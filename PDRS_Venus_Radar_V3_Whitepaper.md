📑 Technical Whitepaper: PDRS Venus Radar V3

The "Neutral Grid Guard" Algorithm

Version: 3.0 (Stable)

Objective: Real-time risk detection for Neutral Futures Grid Bots.

1. The Core Problem: "Lag vs. Noise"

Every grid bot trader faces the same dilemma:

1H Candles are too slow. By the time a candle closes, the pump is over, and your grid is busted.

15m Candles are too noisy. A random 3% wick triggers a "Stop Loss," killing a profitable grid unnecessarily.

The Solution: High-Res Stability Architecture
Venus Radar V3 uses a hybrid approach:

Base Data: 15m Candles (Updates every 15 minutes).

Smoothing Logic: We apply a 4x Period Multiplier to all indicators.

The Math: An SMA-20 on the 1H chart is mathematically simulated by an SMA-80 on the 15m chart.

Result: We get the freshness of 15m data with the reliability of 1H trends.

2. Market Selection Logic (The Universe)

We do not scan the entire market. Scanning 500+ pairs introduces latency.
Instead, we run a "Volatility & Liquidity Filter" every 10 minutes:

Liquidity Gate: quoteVolume > $5,000,000 (24h).

Why? Low cap wicks are fake. We filter them out to prevent false positives.

Volatility Sorting: Rank by Abs(24h_Change).

Selection: Top 40 pairs.

Why 40? Empirical data suggests that at any given moment, only ~20-30 assets are "in play." 40 provides a safe buffer while keeping processing time under 2 seconds.

3. The Scoring Engine (PPAS)

The Potential Pump Alert Score (PPAS) is a weighted sum (0-100).
In V3, we refactored weights to punish Trend and tolerate Noise.

Formula: $PPAS = \sum (Metric \times Weight)$

Metric

Name

Weight (V3)

Role

RP

Rebound Probability

25%

The Kill Switch. Detects one-way breakouts.

TAMS

TA Momentum Score

15%

RSI + ADX + Trend logic.

VR

Volatility Ratio

10%

Grid bots like volatility, unless it breaks structure.

LVR

Liquidation Risk

10%

Volume spike anomalies.

SBR

Buy/Sell Pressure

10%

Sentiment proxy.

VPR

Volume Ratio

10%

Short-term vs. Long-term volume.

HMS/OCAI

Noise Filters

5% each

Reduced impact.

LAF/SCI

Base Metrics

5% each

Reduced to lower the "noise floor."

4. The "Secret Sauce": Exponential Deviation Penalty

This is the most controversial part of our algorithm. We moved from Linear to Exponential Penalty for price deviation.

We define "Deviation" as the % distance from the 200-candle moving average (on 15m).

Linear (Old): $Penalty = Dev \times 2.5$

Exponential (New): $Penalty = |Dev|^{1.5} \times 1.2$

The Impact:

Dev = 10%: Penalty is ~38 pts. (RP stays high -> Grid Continues).

Logic: A 10% move is fine for a wide grid. Don't stop the bot.

Dev = 20%: Penalty is ~107 pts. (RP crashes to 0 -> GRID PAUSED).

Logic: A 20% deviation is a breakout. The mean reversion probability drops to near zero.

Debate Topic: Is the exponent 1.5 too aggressive? Should we use 1.3 for high-volatility alts?

5. Rebound Prediction (The "4.5x" Theory)

We predict the "Max Pump" and "Max Dump" levels to help users set Grid Upper/Lower limits.

The Algo:

Calculate ATR (Average True Range) on 15m.

Scale to Daily: $ATR_{Daily} \approx ATR_{15m} \times 5.0$.

The Multiplier (M): We use M = 4.5.

Hypothesis: Based on 2024-2025 data, Meme/Low-Cap coins typically exhaust momentum after moving 4.5x their Daily ATR in a single session.

Max Pump = $Price + (4.5 \times ATR_{Daily})$

Max Dump = $Price - (4.5 \times ATR_{Daily})$

6. Smart Mute (Anti-Spam State Machine)

To prevent "Alert Fatigue," the radar uses a state machine logic:

Cooldown: 4 Hours per coin.

Override: The silence is BROKEN immediately if:

Risk Level escalates (Warning $\to$ HIGH).

PPAS Score jumps by +5 points (e.g., 85 $\to$ 90).

Open for Debate 🗣️

We are releasing this logic to the community.

Is the 4.5x ATR Multiplier too conservative for current meme super-cycles?

Should Volume weight be higher than Trend (TAMS) for pump detection?

Is Exponential Penalty better than a hard Threshold Cutoff?

Let us know your thoughts below. 👇