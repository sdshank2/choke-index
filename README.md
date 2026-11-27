# NFL Choke Index (`choke_index.py`)

A Python script that pulls live play-by-play win probability data from ESPN's public API to quantify and compare NFL collapses.

Unlike traditional comeback stats that only look at the largest point deficit or peak win probability, the **NFL Choke Index** measures both **how long a team dominated the game** and **how violently the lead collapsed**.

---

## How the Metrics Work

For every snap $i$ in a game, the script tracks the losing team's pre-snap win probability ($WP_i$) and the game-clock seconds elapsed before the next snap ($\Delta t_i$).

### 1. Sustained Dominance Metrics

* **Per-Play Mean ($\mu_{\text{play}}$):** The unweighted average of the losing team's win probability across all $N$ snaps. This treats a 2-second spike and a 40-second huddle equally.

  $$\mu_{\text{play}} = \frac{1}{N} \sum_{i=1}^{N} WP_i$$

* **Clock-Weighted Mean ($\mu_{\text{time}}$):** Win probability weighted strictly by game-clock seconds elapsed ($\Delta t_i$) between snaps. This ignores plays where the clock stopped ($\Delta t_i = 0$).

  $$\mu_{\text{time}} = \frac{\sum_{i=1}^{N} WP_i \cdot \Delta t_i}{\sum_{i=1}^{N} \Delta t_i}$$

* **Active-Time Mean (Primary Dominance Score):** Gives every snap a 5-second baseline time increment plus the clock runoff before the next play ($5 + \Delta t_i$). This ensures clock-stopping plays still count while rewarding sustained clock control.

  $$\text{Active-Time Mean} = \frac{\sum_{i=1}^{N} WP_i \cdot (5 + \Delta t_i)}{\sum_{i=1}^{N} (5 + \Delta t_i)}$$

* **Hybrid 50/50 Mean:** The arithmetic mean of the Per-Play Mean and Clock-Weighted Mean, balancing hurry-up play volume against broadcast clock time.

  $$\text{Hybrid 50/50 Mean} = \frac{\mu_{\text{play}} + \mu_{\text{time}}}{2}$$

* **Filtered Clock Mean:** Strips out pure clock-management plays (spikes and kneel-downs, leaving active snap set $S$) and merges their elapsed clock time ($\Delta t_i^*$) into the preceding competitive snap.

  $$\text{Filtered Clock Mean} = \frac{\sum_{i \in S} WP_i \cdot \Delta t_i^*}{\sum_{i \in S} \Delta t_i^*}$$

### 2. Collapse Velocity & Choke Index

* **Biggest Single-Play Swing:** The largest one-play drop in losing-team win probability, including the exact play number, game clock timestamp, and play-by-play description.

  $$\Delta WP_{\max} = \max_{i} \left(WP_i - WP_{i+1}\right)$$

* **Worst 5-Minute Collapse:** The steepest drop in losing-team win probability inside any 300-second (5-minute) window of active game clock ($t_j - t_i \le 300$).

  $$\text{Collapse}_{5\text{m}} = \max_{t_j - t_i \le 300} \left(WP_i - WP_j\right)$$

* **Choke Index (0–200 Scale):** Combines full-game dominance with late-game collapse velocity:

$$\text{Choke Index} = \text{Active-Time Mean} \times \left(1 + \frac{\text{Collapse}_{5m}}{100}\right)$$

---

## Setup & Usage

1. **Install dependencies:**
   ```bash
   pip install requests roman
   ```
2. **Add games:** Grab the 9-digit Event ID from any ESPN NFL game URL and add it to the `games_to_check` list at the bottom of `choke_index.py`.
3. **Run the script:**
   ```bash
   python choke_index.py
   ```
