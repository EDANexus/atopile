# This file is part of the faebryk project
# SPDX-License-Identifier: MIT

"""
This file contains a faebryk sample.
"""

import logging

import faebryk.library._F as F
from faebryk.core.module import Module
from faebryk.exporters.pcb.kicad.transformer import PCB_Transformer
from faebryk.exporters.pcb.layout.absolute import LayoutAbsolute
from faebryk.exporters.pcb.layout.typehierarchy import LayoutTypeHierarchy
from faebryk.libs.brightness import TypicalLuminousIntensity
from faebryk.libs.examples.pickers import add_example_pickers
from faebryk.libs.library import L

logger = logging.getLogger(__name__)

# App --------------------------------------------------------------------------


class App(Module):
    class PowerButton(Module):
        switch = L.f_field(F.Switch(F.Electrical))()
        power_in: F.ElectricPower
        power_switched: F.ElectricPower

        @L.rt_field
        def can_bridge(self):
            return F.can_bridge_defined(self.power_in, self.power_switched)

        def __preinit__(self):
            self.power_in.hv.connect_via(self.switch, self.power_switched.hv)
            self.power_in.lv.connect(self.power_switched.lv)
            self.power_in.connect_shallow(self.power_switched)

    led: F.PoweredLED
    battery: F.Battery
    power_button: PowerButton

    @L.rt_field
    def transform_pcb(self):
        return F.has_layout_transform(transform_pcb)

    def __preinit__(self) -> None:
        self.led.power.connect_via(self.power_button, self.battery.power)

        # Parametrize
        self.led.led.color.merge(F.LED.Color.YELLOW)
        self.led.led.brightness.merge(
            TypicalLuminousIntensity.APPLICATION_LED_INDICATOR_INSIDE.value.value
        )

    def __postinit__(self) -> None:
        for m in self.get_children_modules(types=Module):
            add_example_pickers(m)


# PCB layout etc ---------------------------------------------------------------


def transform_pcb(transformer: PCB_Transformer):
    app = transformer.app
    assert isinstance(app, App)

    # Layout
    Point = F.has_pcb_position.Point
    L = F.has_pcb_position.layer_type

    layout = LayoutTypeHierarchy(
        layouts=[
            LayoutTypeHierarchy.Level(
                mod_type=F.PoweredLED,
                layout=LayoutAbsolute(Point((25, 5, 0, L.TOP_LAYER))),
                children_layout=LayoutTypeHierarchy(
                    layouts=[
                        LayoutTypeHierarchy.Level(
                            mod_type=F.LED, layout=LayoutAbsolute(Point((0, 0)))
                        ),
                        LayoutTypeHierarchy.Level(
                            mod_type=F.Resistor,
                            layout=LayoutAbsolute(Point((-5, 0, 180))),
                        ),
                    ]
                ),
            ),
            LayoutTypeHierarchy.Level(
                mod_type=F.Battery,
                layout=LayoutAbsolute(Point((25, 35, 0, L.TOP_LAYER))),
            ),
            LayoutTypeHierarchy.Level(
                mod_type=F.Switch(F.Electrical),
                layout=LayoutAbsolute(Point((35, 10, 45, L.TOP_LAYER))),
            ),
        ]
    )
    app.add(F.has_pcb_layout_defined(layout))
    app.add(F.has_pcb_position_defined(Point((50, 50, 0, L.NONE))))

    app.add(
        F.has_pcb_routing_strategy_greedy_direct_line(
            F.has_pcb_routing_strategy_greedy_direct_line.Topology.DIRECT
        )
    )

    transformer.set_pcb_outline_complex(
        geometry=transformer.create_rectangular_edgecut(
            width_mm=50,
            height_mm=50,
            origin=(50, 50),
        ),
        remove_existing_outline=True,
    )
