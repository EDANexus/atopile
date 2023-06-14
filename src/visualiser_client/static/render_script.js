const { shapes, util, dia, anchors } = joint;

// Visual settings for the visualizer
let settings_dict = {
    common: {
        backgroundColor: 'rgba(224, 233, 227, 0.3)',
        gridSize: 5,
        parentPadding: 50,
        fontFamily: "sans-serif",
        labelHorizontalMargin: 80,
        labelVerticalMargin: 40,
    },
    component : {
        strokeWidth: 2,
        fontSize: 10,
        fontWeight: "normal",
        defaultWidth: 60,
        portPitch: 20,
        defaultHeight: 50,
        pin: {
            labelFontSize: 10,
        }
    },
    block : {
        strokeWidth: 2,
        boxRadius: 5,
        strokeDasharray: '4,4',
        label: {
            fontSize: 12,
            fontWeight: "normal",
        }
    },
    link: {
        strokeWidth: 1,
        color: "blue"
    },
    stubs: {
        fontSize: 10,
    }
}

let opposite_direction = {
    "top": "bottom",
    "bottom": "top",
    "left": "right",
    "right": "left"
}

// Base class for the visual elements
class AtoElement extends dia.Element {
    defaults() {
        return {
            ...super.defaults,
            hidden: false,
        };
    }

    isHidden() {
        return Boolean(this.get("hidden"));
    }

    static isAtoElement(shape) {
        return shape instanceof AtoElement;
    }
}

// Class for a component
class AtoComponent extends AtoElement {
    defaults() {
        return {
            ...super.defaults(),
            type: "AtoComponent",
            size: { width: 2 * settings_dict["common"]["labelHorizontalMargin"],
                    height: 2 * settings_dict["common"]["labelVerticalMargin"] },
            attrs: {
                body: {
                    fill: "white",
                    z: 10,
                    stroke: "black",
                    strokeWidth: settings_dict["component"]["strokeWidth"],
                    width: "calc(w)",
                    height: "calc(h)",
                    rx: 5,
                    ry: 5
                },
                label: {
                    text: "Component",
                    fill: "black",
                    fontSize: settings_dict["component"]["fontSize"],
                    fontWeight: settings_dict["component"]["fontWeight"],
                    textVerticalAnchor: "middle",
                    textAnchor: "middle",
                    fontFamily: settings_dict["common"]["fontFamily"],
                    x: "calc(w/2)",
                    y: "calc(h/2)"
                }
            }
        };
    }

    preinitialize() {
        this.markup = util.svg`
            <rect @selector="body" />
            <text @selector="label" />
        `;
    }

    fitAncestorElements() {
        var padding = settings_dict['common']['parentPadding'];
        this.fitParent({
            deep: true,
            padding: {
                top: padding,
                left: padding,
                right: padding,
                bottom: padding
            }
        });
    }
}

// Class for a block
// For the moment, blocks and components are separate.
// We might want to combine them in the future.
class AtoBlock extends dia.Element {
    defaults() {
        return {
            ...super.defaults,
            type: "AtoBlock",
            size: { width: 10, height: 10 },
            collapsed: false,
            attrs: {
            body: {
                fill: "transparent",
                stroke: "#333",
                strokeWidth: settings_dict["block"]["strokeWidth"],
                strokeDasharray: settings_dict["block"]["strokeDasharray"],
                width: "calc(w)",
                height: "calc(h)",
                rx: settings_dict["block"]["boxRadius"],
                ry: settings_dict["block"]["boxRadius"],
            },
            label: {
                text: "Block",
                fill: "#333",
                textVerticalAnchor: "top",
                fontFamily: settings_dict['common']['fontFamily'],
                fontSize: settings_dict['block']['label']['fontSize'],
                fontWeight: settings_dict["block"]["fontWeight"],
                textAnchor: 'start',
                x: 8,
                y: 8
            }
        }
      };
    }

    preinitialize(...args) {
      this.markup = util.svg`
              <rect @selector="body" />
              <text @selector="label" />
          `;
    }

    updateChildrenVisibility() {
      const collapsed = this.isCollapsed();
      this.getEmbeddedCells().forEach((child) => child.set("hidden", collapsed));
    }

    fitAncestorElements() {
        var padding = 10;
        this.fitParent({
            deep: true,
            padding: {
                top:  padding,
                left: padding,
                right: padding,
                bottom: padding
            }
        });
    }
  }


const cellNamespace = {
    ...shapes,
    AtoElement,
    AtoComponent,
    AtoBlock
};

function getPortLabelPosition(port) {
    switch (port['location']) {
        case "top":
            return [0, 8];
        case "bottom":
            return [0, -8];
        case "left":
            return [5, 0];
        case "right":
            return [-5, 0];
        default:
            return [0, 0];
    };
}

function getPortLabelAnchor(port) {
    switch (port['location']) {
        case "top":
            return 'end';
        case "bottom":
            return 'start';
        case "left":
            return 'start';
        case "right":
            return 'end';
        default:
            return 'middle';
    }
};

function getPortLabelAngle(port) {
    switch (port['location']) {
        case "top":
            return -90;
        case "bottom":
            return -90;
        case "left":
            return 0;
        case "right":
            return 0;
        default:
            return 0;
    };
};

function getPortPosition(port) {
    switch (port['location']) {
        case "top":
            return {
                name: 'line',
                args: {
                    start: { x: settings_dict['common']['labelHorizontalMargin'], y: 0 },
                    end: { x: ('calc(w - ' + settings_dict['common']['labelHorizontalMargin'] + ')'), y: 0 }
                },
            };
        case "bottom":
            return {
                name: 'line',
                args: {
                    start: { x: settings_dict['common']['labelHorizontalMargin'], y: 'calc(h)' },
                    end: { x: ('calc(w - ' + settings_dict['common']['labelHorizontalMargin'] + ')'), y: 'calc(h)' }
                },
            };
        case "left":
            return {
                name: 'line',
                args: {
                    start: { x: 0, y: settings_dict['common']['labelVerticalMargin']},
                    end: { x: 0, y: ('calc(h - ' + settings_dict['common']['labelVerticalMargin'] + ')')}
                },
            };
        case "right":
            return {
                name: 'line',
                args: {
                    start: { x: 'calc(w)', y: settings_dict['common']['labelVerticalMargin'] },
                    end: { x: 'calc(w)', y: ('calc(h - ' + settings_dict['common']['labelVerticalMargin'] + ')')}
                },
            };
        default:
            return 0;
    };
};

function addPortsAndPins(element, port_list) {
    // Dict of all the port for the element
    let port_groups = {};

    let pin_nb_by_port = {};
    // Create the different ports
    for (let port of port_list) {

        let port_label_position = [];
        let port_anchor = "";
        let port_angle = 0;
        let port_position = {};
        port_label_position = getPortLabelPosition(port);
        port_anchor = getPortLabelAnchor(port);
        port_angle = getPortLabelAngle(port);
        port_position = getPortPosition(port);


        pin_nb_by_port[port['location']] = 0;

        port_groups[port['name']] = {
            position: port_position,
            attrs: {
                portBody: {
                    magnet: true,
                    r: 2,
                    fill: '#FFFFFF',
                    stroke:'#023047',
                },
            },
            label: {
                position: {
                    args: {
                        x: port_label_position[0],
                        y: port_label_position[1],
                        angle: port_angle,
                    }, // Can't use inside/outside in combination
                    //name: 'inside'
                },
                markup: [{
                    tagName: 'text',
                    selector: 'label',
                    className: 'label-text'
                }]
            },
            markup: [{
                tagName: 'circle',
                selector: 'portBody'
            }]
        };

        // While we are creating the port, add the pins in the element
        for (let pin of port['pins']) {
            pin_nb_by_port[port['location']] += 1;
            element.addPort({
                id: pin["uuid"],
                group: port['name'],
                attrs: {
                    label: {
                        text: pin['name'],
                        fontFamily: settings_dict['common']['fontFamily'],
                        fontSize: settings_dict['component']['pin']['labelFontSize'],
                        textAnchor: port_anchor,
                    },
                },
            });
            pin_to_element_association[pin["uuid"]] = element["id"];
        }
    };

    let top_pin_number = 'top' in pin_nb_by_port ? pin_nb_by_port.top : undefined;
    let bottom_pin_number = 'bottom' in pin_nb_by_port ? pin_nb_by_port.bottom : undefined;
    let left_pin_number = 'left' in pin_nb_by_port ? pin_nb_by_port.left : undefined;
    let right_pin_number = 'right' in pin_nb_by_port ? pin_nb_by_port.right : undefined;

    let max_width = Math.max(top_pin_number || -Infinity, bottom_pin_number || -Infinity);
    let max_height = Math.max(left_pin_number || -Infinity, right_pin_number || -Infinity);

    let component_width = 2 * settings_dict['common']['labelHorizontalMargin'];
    if (max_width > 0) {
        component_width += settings_dict['component']['portPitch'] * max_width;
    }
    let component_height = settings_dict['component']['defaultHeight'];
    if (max_height > 0) {
        component_height += settings_dict['component']['portPitch'] * max_height;
    }
    element.resize(component_width, component_height);

    // Add the ports list to the element
    element.prop({"ports": { "groups": port_groups}});
}

function addLinks(links) {
    for (let link of links) {
        var added_link = new shapes.standard.Link({
            source: {
                id: pin_to_element_association[link['source']],
                port: link['source']
            },
            target: {
                id: pin_to_element_association[link['target']],
                port: link['target']
            }
        });
        added_link.attr({
            line: {
                'stroke': settings_dict['link']['color'],
                'stroke-width': settings_dict['link']['strokeWidth'],
                targetMarker: {'type': 'none'},
            },
            z: 0
        });
        added_link.router('manhattan', {
            perpendicular: true,
            step: settings_dict['common']['gridSize'],
        });

        added_link.addTo(graph);

        var verticesTool = new joint.linkTools.Vertices();
        var segmentsTool = new joint.linkTools.Segments();
        var boundaryTool = new joint.linkTools.Boundary();

        var toolsView = new joint.dia.ToolsView({
            tools: [verticesTool, boundaryTool]
        });

        var linkView = added_link.findView(paper);
        linkView.addTools(toolsView);
        linkView.hideTools();
    }
}

function addStubs(stubs) {
    for (let stub of stubs) {
        console.log(stub);
        var added_stub = new shapes.standard.Link({id: stub['uuid']});
        added_stub.prop('source', {
            id: pin_to_element_association[stub['source']],
            port: stub['source']});
        if (stub['position']) {
            added_stub.prop('target', stub['position']);
        } else {
            added_stub.prop('target', { x: 10, y: 10 });
        }
        added_stub.router('manhattan', {
            startDirections: [stub['direction']],
            endDirections: [opposite_direction[stub['direction']]],
            perpendicular: true,
            step: settings_dict['common']['gridSize'],
        });
        added_stub.attr('root/title', 'joint.shapes.standard.Link');
        added_stub.attr({
            line: {
                'stroke': settings_dict['link']['color'],
                'stroke-width': settings_dict['link']['strokeWidth'],
                //targetMarker: {'type': 'none'},
            },
            z: 0
        });
        let label_offset;
        (stub['direction'] == 'bottom') ? label_offset = 10 : label_offset = -10;
        added_stub.appendLabel({
            attrs: {
                text: {
                    text: stub['name'],
                    fontFamily: settings_dict['common']['fontFamily'],
                    fontSize: settings_dict['stubs']['fontSize'],
                }
            },
            position: {
                distance: 1,
                offset: {
                    x: 0,
                    y: label_offset
                },
                angle: 0,
                args: {
                    keepGradient: false
                }
            }
        });
        added_stub.addTo(graph);
    };
}

function createComponent(title, uuid, ports_dict, x, y) {
    const component = new AtoComponent({
        id: uuid,
        attrs: {
            label: {
                text: title
            }
        }
    });

    addPortsAndPins(component, ports_dict);

    component.addTo(graph);
    component.position(x, y, { parentRelative: true });
    return component;
}

function createBlock(title, uuid, ports_dict, x, y) {
    const block = new AtoBlock({
        id: uuid,
        attrs: {
            label: {
                text: title,
            }
        }
    });

    addPortsAndPins(block, ports_dict);

    block.addTo(graph);
    block.position(x, y, { parentRelative: false });
    return block;
}

function addElementToElement(block_to_add, to_block) {
    to_block.embed(block_to_add);
}

function getElementTitle(element) {
    if (element['instance_of'] != null) {
        return`${element['name']} \n(${element['instance_of']})`;
    } else {
        return element['name'];;
    }
}

function renderDataFromBackend(data, is_root = true, parent = null) {

    // Create the list of all the created elements
    let dict_of_elements = {};

    for (let element of data) {
        // FIXME: this default positioning is shit
        let x = 100;
        let y = 100;

        if (element['position']) {
            x = element['position']['x'];
            y = element['position']['y'];
        }

        var created_element = null;

        if (element['type'] == 'component') {
            let title = getElementTitle(element);
            created_element = createComponent(title, element['uuid'], element['ports'], x, y);
            dict_of_elements[element['uuid']] = created_element;
            // FIXME: this is stupildy inefficent. We should be calling fitEmbeds once instead, but it didn't work
            created_element.fitAncestorElements();
        }

        // If it is a block, create it
        else if (element['type'] == 'module') {
            let title = getElementTitle(element);
            created_element = createBlock(title, element['uuid'], element['ports'], x, y);
            dict_of_elements[element['uuid']] = created_element;

            // Iterate over the included elements to create them
            let returned_dict = renderDataFromBackend(element['blocks'], false, created_element);
            // Add the returned list to the element list and add all sub-elements to it's parent
            dict_of_elements = { ...dict_of_elements, ...returned_dict };

            addLinks(element['links']);
            addStubs(element['stubs']);
            created_element.fitAncestorElements();
        }

        else {
            // raise an error because we don't know what to do with this element
            // TODO: raise an error
            console.log('Unknown element type:'+ element['type']);
        }

        if (parent) {
            addElementToElement(created_element, parent);
        }
    }

    for (let e_name in dict_of_elements) {
        // FIXME: this is stupildy inefficent. We should be calling fitEmbeds once instead, but it didn't work
        dict_of_elements[e_name].fitAncestorElements();
    }

    return dict_of_elements;
}

const graph = new dia.Graph({}, { cellNamespace });
const paper = new joint.dia.Paper({
    el: document.getElementById('atopilePaper'),
    model: graph,
    width: '100%',
    height: '100%',
    gridSize: settings_dict['common']['gridSize'],
    drawGrid: true,
    background: {
        color: settings_dict["common"]["backgroundColor"]
    },
    interactive: true,
    cellViewNamespace: cellNamespace,
});

function fill_paper() {
    paper.setDimensions(window.innerWidth, window.innerHeight);
}

window.onload = fill_paper;
window.onresize = fill_paper;

let pin_to_element_association = {};
let element_dict = {};

paper.on('link:mouseenter', function(linkView) {
    linkView.showTools();
    linkView.highlight();
});

paper.on('link:mouseleave', function(linkView) {
    linkView.hideTools();
    linkView.unhighlight();
});

paper.on('cell:pointerup', function(cell, evt, x, y) {
    console.log(cell);
    let requestOptions = {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: {}
    };
    if (cell.model instanceof AtoComponent) {
        requestOptions.body = JSON.stringify({
            id: cell.model.attributes.id,
            x: cell.model.attributes.position.x,
            y: cell.model.attributes.position.y,
        });
        fetch('/api/view/move', requestOptions);
    } else if (cell.model instanceof shapes.standard.Link) {
        requestOptions.body = JSON.stringify({
            id: cell.model.attributes.id,
            x: cell.targetPoint.x,
            y: cell.targetPoint.y,
        });
        fetch('/api/view/move', requestOptions);
    }
});

graph.on('change:position', function(cell) {
    // `fitAncestorElements()` method is defined at `joint.shapes.container.Base` in `./joint.shapes.container.js`
    cell.fitAncestorElements();
});

async function loadData() {
    const response = await fetch('/api/view');
    const vis_dict = await response.json();

    console.log(vis_dict);
    element_dict = renderDataFromBackend(vis_dict);
}

loadData();
