#! /usr/bin/env python3

import schemdraw
import schemdraw.elements as elm

with schemdraw.Drawing(canvas="svg", file="diagram.svg") as d:
    elm.style(elm.STYLE_IEC)

    header = elm.Header(rows=5, style="screw", pinsleft=["5", "4", "B", "3", "2"])

    elm.Line().at(header.pin1).length(2)
    diode = elm.Diode().label("1N4148")
    elm.Resistor().down(2).label("$2.2 k\\Omega$\n0.5 W")
    zener = elm.Zener().reverse().length(2).label("8.2 V\n0.5 W")

    elm.Line().right(1.45)
    opto = elm.Optocoupler().label("PC817C")
    elm.Line().at(opto.cathode).tox(diode.start)
    dot4 = elm.Dot(open=False)
    elm.Line().toy(header.pin2)
    elm.Line().to(header.pin2)

    elm.Line().right(1).at(opto.emitter)
    gnd = elm.Ground()

    elm.Line().right(1).at(opto.collector)
    elm.Line().toy(zener.start)
    elm.Dot()
    with d.hold():
        elm.Line().right()
        doorbell_input = elm.Dot(open=True).label("GPIO14 / High")
    elm.Resistor().toy(diode.start).label("$10 k\\Omega$\n0.25 W")
    elm.Dot(open=True).label("3.3 V")

    elm.Line().at(dot4.center).down().length(2.75)
    elm.Line().right().length(3.5)

    comp = elm.Ic(
        size=(4.8, 2),
        pins=[
            elm.IcPin(name="NO", side="left"),
            elm.IcPin(name="COM", side="left"),
            elm.IcPin(name="NC", side="left"),
            elm.IcPin(name="DC+", side="right"),
            elm.IcPin(name="IN", side="right"),
            elm.IcPin(name="DC-", side="right"),
        ],
        label="GTIWUNG 5V\nRelay Module",
    ).anchor("COM")
    with d.hold():
        h = (
            elm.Header(rows=3, cols=1, style="square")
            .at((comp.center.x, comp.center.y - 0.7))
            .up()
            .anchor("pin2")
            .scale(0.5)
            .label("L", loc="T")
            .label("H", loc="B")
        )
        elm.Jumper().at(h.pin1).fill("lightgray").scale(0.5)

    elm.Line().at(header.pin3).length(1.5)
    elm.Line().toy(comp.NO)
    elm.Line().to(comp.NO)

    elm.Wire("|-").at(comp["DC-"]).to(gnd.start)
    elm.Wire("-|").at(comp["IN"]).to((doorbell_input.start.x, doorbell_input.start.y - 1))
    relay_port = elm.Dot(open=True).label("GPIO10 / High")

    elm.Line().at(comp["DC+"]).right().length(2)
    elm.Line().toy(gnd.start)
    elm.Dot(open=True).label("5 V")
