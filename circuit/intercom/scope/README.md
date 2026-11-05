# Oscilloscope Recordings

This directory contains three oscilloscope recordings taken from a door entry system to observe the electrical signals associated with the door release, doorbell, and a simulated load.

## Measurement Setup

Measurements were taken between terminals **4–B** and **4–5**, with terminal **4** always used as the voltage reference.

## Recordings

| File | Measurement | Description |
|---|---|---|
| `splg0001.csv` | B relative to 4 | Voltage recorded while the **door release button** is pressed. Captures the resulting voltage changes at terminal B. |
| `splg0002.csv` | 5 relative to 4 | Voltage recorded while the **doorbell is rung**. Captures the signal associated with the doorbell activation. |
| `splg0003.csv` | B relative to 4 | Voltage recorded while terminals **4 and B are connected through a 1 $\Omega$ shunt resistor**. Captures the system's response to the applied load. |
