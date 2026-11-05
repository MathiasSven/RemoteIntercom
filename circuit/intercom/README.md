# Contera Starbell 1000 C

The following terminal descriptions and voltage information come from the [Electropescador product page][source]:

| Terminal | Connection |
| --- | --- |
| 2 | Red handset wire |
| 3 | Green handset wire |
| 4 | Black handset wire, buzzer return, and building common |
| B | Building power supply |
| 5 | Doorbell wires |

According to the source, terminal 4 is common, not a fixed negative, and approximately 14 V DC between B and 2 or 3 is normal. Confirm the connections against the diagram in the manual before installation.

## Files

- `diagram.avif`: Starbell 1000 C wiring diagram showing the door release and doorbell connections.
- `ref-front.avif` and `ref-back.avif`: photographs of the intercom circuit board and its wiring, viewed from the component and solder sides.
- `scope/`: oscilloscope recordings, plots, and a graph-generation script. See [scope/README.md](scope/README.md) for the measurement setup and recording descriptions. The `.slg` files are recordings, the `.csv` files contain exported samples, and `BIN2csv/` contains a Windows converter executable.

## Reference

[source]: https://electropescador.pt/material-eletrico/circuito-porteiro/porteiro-e-videoporteiro/33256-telefone-porteiro-contera-starbell-1000-c.html "Electropescador: Contera Starbell 1000 C"

- [Contera Starbell 1000 C — Electropescador][source]
