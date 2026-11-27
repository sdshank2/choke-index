from datetime import datetime
import requests
import roman

def analyze_game_choke(event_id):
    # 1. Fetch game summary
    summary_url = f"https://site.api.espn.com/apis/site/v2/sports/football/nfl/summary?event={event_id}"
    summary_resp = requests.get(summary_url)
    summary_resp.raise_for_status()
    summary_data = summary_resp.json()

    # Determine home vs. away winner/loser (using next(iter()) so markdown never eats brackets)
    first_comp = next(iter(summary_data["header"]["competitions"]))
    competitors = first_comp["competitors"]
    home_team = next(c for c in competitors if c["homeAway"] == "home")
    away_team = next(c for c in competitors if c["homeAway"] == "away")

    home_lost = not home_team.get("winner", False)
    loser_name = home_team["team"]["displayName"] if home_lost else away_team["team"]["displayName"]
    winner_name = away_team["team"]["displayName"] if home_lost else home_team["team"]["displayName"]
    raw_date = first_comp.get("date", "")
    try:
        game_date = datetime.strptime(raw_date[:10], "%Y-%m-%d").strftime("%b %d, %Y")
    except ValueError:
        game_date = "Unknown Date"

    notes = first_comp.get("notes", [])
    season_type = summary_data.get("header", {}).get("season", {}).get("type", 2)
    week_num = summary_data.get("header", {}).get("week", "")

    if notes and next(iter(notes)).get("headline"):
        round_label = next(iter(notes))["headline"]
    elif season_type == 3:
        afc_teams = {"BUF", "MIA", "NE", "NYJ", "BAL", "CIN", "CLE", "PIT", "HOU", "IND", "JAX", "TEN", "DEN", "KC", "LV", "LAC"}
        if week_num == 5:
            sb_num = roman.toRoman(int(raw_date[:4]) - 1966)
            round_label = f"Super Bowl {sb_num}"
        else:
            playoff_rounds = {1: "Wild Card Round", 2: "Divisional Round", 3: "Conference Championship"}
            base_round = playoff_rounds.get(week_num, f"Postseason Week {week_num}")
            abbr = home_team.get("team", {}).get("abbreviation", "")
            conf_name = "AFC" if abbr in afc_teams else "NFC"
            round_label = f"{conf_name} {base_round}".strip()
    else:
        round_label = f"Regular Season (Week {week_num})"

    # Map play IDs to their game clock, play text, and play type
    play_lookup = {}
    drives_data = summary_data.get("drives", {})
    all_drives = list(drives_data.get("previous", []))
    if "current" in drives_data:
        all_drives.append(drives_data["current"])

    for drive in all_drives:
        for play in drive.get("plays", []):
            play_id = str(play["id"])
            seq = int(play.get("sequenceNumber", 0))
            quarter = play.get("period", {}).get("number", 1)
            clock_str = play.get("clock", {}).get("displayValue", "0:00")
            raw_text = play.get("text", "No play description available")

            try:
                mins, secs = map(int, clock_str.split(":"))
            except ValueError:
                mins, secs = 0, 0

            # Calculate total seconds elapsed in regulation (0 to 3600)
            if quarter <= 4:
                elapsed_game_secs = (quarter - 1) * 900 + (900 - (mins * 60 + secs))
                q_label = f"Q{quarter}"
            else:
                elapsed_game_secs = 3600 + (quarter - 5) * 600 + (600 - (mins * 60 + secs))
                q_label = f"OT{quarter - 4}"

            play_type = play.get("type", {}).get("text", "").lower()
            play_text = raw_text.lower()
            is_clock_play = (
                "kneel" in play_type
                or "spike" in play_type
                or "kneels" in play_text
                or "spiked" in play_text
            )

            play_lookup[play_id] = {
                "seq": seq,
                "elapsed_game_secs": elapsed_game_secs,
                "is_clock_play": is_clock_play,
                "timestamp": f"{q_label} {clock_str}",
                "text": raw_text,
            }

    # 2. Fetch ESPN's win probability feed
    wp_url = f"https://sports.core.api.espn.com/v2/sports/football/leagues/nfl/events/{event_id}/competitions/{event_id}/probabilities?limit=300"
    wp_resp = requests.get(wp_url)
    wp_resp.raise_for_status()
    wp_items = wp_resp.json().get("items", [])

    # Align win probabilities with timestamps and descriptions
    timeline = []
    for item in wp_items:
        play_ref = item.get("play", {}).get("$ref", "")
        play_id = play_ref.split("/")[-1].partition("?")[0]

        if play_id in play_lookup:
            loser_wp = item["homeWinPercentage"] if home_lost else item["awayWinPercentage"]
            info = play_lookup[play_id]
            timeline.append({
                "seq": info["seq"],
                "wp": loser_wp * 100,
                "t": info["elapsed_game_secs"],
                "is_clock_play": info["is_clock_play"],
                "timestamp": info["timestamp"],
                "text": info["text"],
            })

    if not timeline:
        print(f"No aligned play-by-play win probability data found for Event ID {event_id}.")
        return

    # Sort chronologically and compute delta_t
    timeline.sort(key=lambda x: x["seq"])
    max_t = max(3600, timeline[-1]["t"])

    for i in range(len(timeline)):
        timeline[i]["play_num"] = i + 1
        if i < len(timeline) - 1:
            dt = max(0, timeline[i + 1]["t"] - timeline[i]["t"])
        else:
            dt = max(0, max_t - timeline[i]["t"])
        timeline[i]["dt"] = dt

    # --- CALCULATE ALL THREE FORMULAS ---

    n_plays = len(timeline)
    mu_play = sum(p["wp"] for p in timeline) / n_plays

    total_time = sum(p["dt"] for p in timeline)
    mu_time = sum(p["wp"] * p["dt"] for p in timeline) / total_time

    # Formula 1: Action + Clock Weight (5s baseline + delta_t)
    c = 5
    score_1 = sum(p["wp"] * (c + p["dt"]) for p in timeline) / sum((c + p["dt"]) for p in timeline)

    # Formula 2: 50/50 Blend
    score_2 = (mu_play + mu_time) / 2

    # Formula 3: Filtered Time-Weighted Average
    filtered = []
    for p in timeline:
        if p["is_clock_play"] and filtered:
            filtered[-1]["dt"] += p["dt"]
        elif not p["is_clock_play"]:
            filtered.append({"wp": p["wp"], "dt": p["dt"]})

    score_3 = sum(p["wp"] * p["dt"] for p in filtered) / sum(p["dt"] for p in filtered)

    # --- COLLAPSE VELOCITY & PLAY TRACKING ---

    # 1. Biggest single-play drop + play details
    max_single_drop = 0
    swing_play = None
    wp_before = 0
    wp_after = 0

    for i in range(len(timeline) - 1):
        drop = timeline[i]["wp"] - timeline[i + 1]["wp"]
        if drop > max_single_drop:
            max_single_drop = drop
            swing_play = timeline[i+1]
            wp_before = timeline[i]["wp"]
            wp_after = timeline[i + 1]["wp"]

    # 2. Steepest collapse inside any 5-minute (300-second) window + timestamps
    max_5min_drop = 0
    collapse_start = None
    collapse_end = None

    for i in range(len(timeline)):
        for j in range(i + 1, len(timeline)):
            if timeline[j]["t"] - timeline[i]["t"] <= 300:
                drop = timeline[i]["wp"] - timeline[j]["wp"]
                if drop > max_5min_drop:
                    max_5min_drop = drop
                    collapse_start = timeline[i]
                    collapse_end = timeline[j]

    # Combined Choke Index (Dominance * Collapse Multiplier)
    choke_index = score_1 * (1 + (max_5min_drop / 100))

    # --- PRINT RESULTS ---
    print(f"Matchup: {winner_name} def. {loser_name} (Event ID: {event_id})")
    print(f"Context: {game_date} | {round_label}")
    print(f"Total Snaps Analyzed: {n_plays} | Peak Loser Win Prob: {max(p['wp'] for p in timeline):.1f}%")
    print("-" * 60)
    print(f"Per-Play Mean:                   {mu_play:.2f}%")
    print(f"Clock-Weighted Mean:             {mu_time:.2f}%")
    print(f"Active-Time Mean (Primary):      {score_1:.2f}%")
    print(f"Hybrid 50/50 Mean:               {score_2:.2f}%")
    print(f"Filtered Clock Mean:             {score_3:.2f}%")
    print("-" * 60)
    print(f"Biggest Single-Play Swing:      -{max_single_drop:.1f}% ({wp_before:.1f}% -> {wp_after:.1f}%)")
    if swing_play:
        print(f"  -> Play #{swing_play['play_num']} [{swing_play['timestamp']}]: {swing_play['text']}")
    print(f"Worst 5-Minute Collapse:        -{max_5min_drop:.1f}%")
    if collapse_start and collapse_end:
        print(f"  -> Window: {collapse_start['timestamp']} ({collapse_start['wp']:.1f}%) to {collapse_end['timestamp']} ({collapse_end['wp']:.1f}%)")
    print(f"Choke Index:                     {choke_index:.2f}\n")


if __name__ == "__main__":
    games_to_check = [
        "401873080",  # 2026: Eagles vs. Cowboys (21-pt comeback)
        "400927752",  # 2017: Patriots vs. Falcons (28-3 SB LI)
        "401437904",  # 2022: Vikings vs. Colts (33-0 comeback)
        "401437998",  # 2023: Jaguars vs. Chargers (27-0 comeback)
        "401131043",  # 2020: Chiefs vs. Texans (24-0 comeback)
        "401437915",  # 2022: Raiders vs. Patriots (Meyers lateral)
    ]

    for event_id in games_to_check:
        analyze_game_choke(event_id)
