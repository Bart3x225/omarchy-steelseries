import QtQuick
import QtQuick.Controls as Controls
import Quickshell
import qs.Commons
import qs.Commons as Commons
import qs.Ui
import "." as SteelSeries
import "FleetModel.js" as Model

Panel {
    id: root
    moduleName: "bart.steelseries"
    ipcTarget: "bart.steelseries"
    manageIpc: false
    Commons.ShellIpc {
        target: root.ipcTarget
        function open(): void { root.open() }
        function close(): void { root.close() }
        function show(): void { root.open() }
        function hide(): void { root.close() }
        function toggle(): void { root.toggle() }
        function selectDevice(id: string): string {
            for (var i = 0; i < root.devices.length; i++) {
                if (root.devices[i].id === id) { root.selectedId = id; root.open(); return "ok" }
            }
            return "not found"
        }
        function showPage(name: string): string { var pages=["details","settings","hardware","history"];var n=pages.indexOf(name);if(n<0)return "invalid";root.page=n;root.open();return "ok" }
        function details(): string { return JSON.stringify({page:root.page,history:root.selected.history,controls:root.selected.controls,config:SteelSeries.SteelSeriesService.config,device: root.selected, batteryLabel: root.batteryLevel, stateText: root.stateText, updatedText: root.updatedText, opened: root.opened, iconCount: repeater.count}) }
    }
    property int page: 0
    property string selectedId: ""
    readonly property var allDevices: SteelSeries.SteelSeriesService.snapshot.devices || []
    readonly property var devices: allDevices.filter(function(d){return (SteelSeries.SteelSeriesService.config.hiddenIds||[]).indexOf(d.id)<0})
    readonly property bool vertical: bar ? bar.vertical : false
    readonly property var selected: {
        for (var i = 0; i < allDevices.length; i++) if (allDevices[i].id === selectedId) return allDevices[i]
        return allDevices.length ? allDevices[0] : {id: "", name: "SteelSeries", state: "absent", battery: -1, charging: false, battery_supported: false, wireless: false, transport: "usb", kind: "device", error: ""}
    }
    readonly property color foreground: bar ? bar.foreground : Commons.Color.foreground
    readonly property int batteryLevel: !SteelSeries.SteelSeriesService.error && selected.state === "connected" ? selected.battery : -1
    readonly property bool low: batteryLevel >= 0 && batteryLevel <= 20 && !selected.charging
    readonly property string stateText: deviceState(selected)
    readonly property string updatedText: SteelSeries.SteelSeriesService.snapshot.updated ? strings.t("updated").arg(new Date(SteelSeries.SteelSeriesService.snapshot.updated * 1000).toLocaleTimeString(Qt.locale(Commons.I18n.formatLocale), "HH:mm:ss")) : strings.t("starting")
    implicitWidth: buttons.implicitWidth
    implicitHeight: buttons.implicitHeight
    onOpenedChanged: if (opened) SteelSeries.SteelSeriesService.refresh()
    Commons.Translations { id: strings; directory: Qt.resolvedUrl("i18n") }
    function deviceState(device) {
        if (SteelSeries.SteelSeriesService.error) return strings.t("error")
        if (device.state !== "connected") return strings.t(device.state)
        if (device.charging) return strings.t("charging")
        return strings.t("connected." + (device.transport === "bluetooth" ? "bluetooth" : device.transport === "wireless" ? "wireless" : "usb"))
    }
    function deviceIcon(kind) {
        if (kind === "headset") return "\uf025"
        if (kind === "mouse") return "\uf8cc"
        if (kind === "keyboard") return "\uf11c"
        if (kind === "mousepad") return "\uf2d0"
        return "\uf11b"
    }
    Grid {
        id: buttons
        columns: root.vertical ? 1 : Math.max(1, repeater.count)
        spacing: 0
        Repeater {
            id: repeater
            model: root.devices.length ? root.devices : [{id:"",name:"SteelSeries",kind:"device",state:"absent",battery:-1,wireless:false,battery_supported:false,charging:false}]
            delegate: BarIconButton {
                id: deviceButton
                required property var modelData
                bar: root.bar
                text: root.deviceIcon(modelData.kind)
                iconComponent: modelData.kind === "mouse" ? mouseArtwork : null
                Component {
                    id: mouseArtwork
                    SteelSeries.MouseIcon { color: deviceButton.active ? deviceButton.activeColor : deviceButton.foreground }
                }
                labelText: SteelSeries.SteelSeriesService.error ? (modelData.wireless ? "—" : "") : Model.deviceLabel(modelData) + (modelData.charging && modelData.battery >= 0 ? " ⚡" : "")
                fixedWidth: vertical ? -1 : implicitWidth
                implicitWidth: vertical ? slotSize : canvasSize + (labelText ? labelMeasure.implicitWidth + Style.space(6) : 0) + Style.space(12)
                active: modelData.state === "connected" && modelData.battery >= 0 && modelData.battery <= SteelSeries.SteelSeriesService.config.lowThreshold && !modelData.charging
                dimmed: modelData.state !== "connected" || SteelSeries.SteelSeriesService.error !== ""
                tooltipText: Model.safeText(modelData.name) + " · " + root.deviceState(modelData)
                onPressed: function(buttonCode) {
                    if (buttonCode === Qt.RightButton) { SteelSeries.SteelSeriesService.refresh(); return }
                    var same = root.selected.id === modelData.id
                    root.selectedId = modelData.id
                    root.page = 0
                    if (same && root.opened) root.close()
                    else root.open()
                }
                Text { id: labelMeasure; visible: false; textFormat: Text.PlainText; text: deviceButton.labelText; font.family: deviceButton.fontFamily; font.pixelSize: deviceButton.fontSize }
            }
        }
    }
    KeyboardPanel {
        id:panel;anchorItem:root;owner:root;bar:root.bar;open:root.opened;focusTarget:panel.loadedContent
        contentWidth:panel.fittedContentWidth(Style.space(430))
        contentHeight:panel.fittedContentHeight(panel.loadedContentHeight,Style.space(650))
        content:PanelKeyCatcher {
            implicitHeight:column.implicitHeight
            anchors.fill:parent
            onCloseRequested:root.close()
            onTabRequested:function(direction){root.switchPanel(direction)}
            onTextKey:function(t){if(t.toLowerCase()==="r")SteelSeries.SteelSeriesService.refresh()}
            Flickable {
                id:flick;anchors.fill:parent;contentWidth:width;contentHeight:column.implicitHeight;clip:true
                boundsBehavior:Flickable.StopAtBounds
                Controls.ScrollBar.vertical:Controls.ScrollBar {}
                Column {
                    id:column;width:flick.width;spacing:Style.space(12)
                    Text {width:parent.width;wrapMode:Text.WordWrap;textFormat:Text.PlainText;text:root.selected.name;color:root.foreground;font.family:Style.font.family;font.pixelSize:Style.font.title}
                    Row {
                        width:parent.width
                        Repeater {
                            model:["details","settings","hardware","history"]
                            delegate:WidgetButton {
                                required property string modelData
                                required property int index
                                width:column.width/4;text:strings.t(modelData);foreground:root.foreground;active:root.page===index
                                onPressed:{root.page=index;flick.contentY=0}
                            }
                        }
                    }
                    Column {
                        visible:root.page===0;width:parent.width;spacing:Style.space(12)
                        Text {width:parent.width;wrapMode:Text.WordWrap;textFormat:Text.PlainText;text:root.stateText;color:root.foreground;font.pixelSize:Style.font.body}
                        Text {textFormat:Text.PlainText;text:root.batteryLevel>=0?root.batteryLevel+"%":strings.t(root.selected.battery_supported?"unavailable":"noBattery");color:root.low?Commons.Color.urgent:root.foreground;font.pixelSize:root.batteryLevel>=0?Style.font.display:Style.font.body}
                        Rectangle {visible:root.batteryLevel>=0;width:parent.width;height:Style.space(7);radius:height/2;color:Qt.alpha(root.foreground,0.15)
                            Rectangle {width:parent.width*Math.max(0,root.batteryLevel)/100;height:parent.height;radius:height/2;color:root.low?Commons.Color.urgent:root.foreground}
                        }
                        Text {width:parent.width;wrapMode:Text.WordWrap;textFormat:Text.PlainText;text:strings.t("connection")+": "+strings.t("transport."+(root.selected.transport==="bluetooth"?"bluetooth":root.selected.transport==="wireless"?"wireless":"usb"));color:root.foreground;font.pixelSize:Style.font.body}
                        Text {visible:!!root.selected.error||!!SteelSeries.SteelSeriesService.error;width:parent.width;wrapMode:Text.WrapAnywhere;textFormat:Text.PlainText;text:String(root.selected.error||SteelSeries.SteelSeriesService.error||"");color:Commons.Color.urgent;font.pixelSize:Style.font.body}
                        Text {width:parent.width;wrapMode:Text.WordWrap;textFormat:Text.PlainText;text:root.updatedText;color:Qt.alpha(root.foreground,0.65);font.pixelSize:Style.font.body}
                        WidgetButton {width:parent.width;text:strings.t("refresh")+(SteelSeries.SteelSeriesService.busy?"…":"");foreground:root.foreground;interactive:!SteelSeries.SteelSeriesService.busy;onPressed:SteelSeries.SteelSeriesService.refresh()}
                    }
                    Loader {width:parent.width;active:root.page===1;visible:active;sourceComponent:Component{SteelSeries.SettingsView{}}}
                    Loader {width:parent.width;active:root.page===2;visible:active;sourceComponent:Component{SteelSeries.HardwareView{device:root.selected}}}
                    Loader {width:parent.width;active:root.page===3;visible:active;sourceComponent:Component{SteelSeries.HistoryView{device:root.selected}}}
                    Text {visible:Object.keys(SteelSeries.SteelSeriesService.snapshot.source_errors||{}).length>0;width:parent.width;wrapMode:Text.WrapAnywhere;textFormat:Text.PlainText;text:JSON.stringify(SteelSeries.SteelSeriesService.snapshot.source_errors||{});color:Commons.Color.urgent;font.pixelSize:Style.font.body}
                    Text {visible:!!SteelSeries.SteelSeriesService.operationResult.message||!!SteelSeries.SteelSeriesService.operationResult.error||SteelSeries.SteelSeriesService.operationResult.ok===true;width:parent.width;wrapMode:Text.WrapAnywhere;textFormat:Text.PlainText;text:String(SteelSeries.SteelSeriesService.operationResult.error||SteelSeries.SteelSeriesService.operationResult.message||strings.t("saved"))+(SteelSeries.SteelSeriesService.operationResult.ok&&SteelSeries.SteelSeriesService.operationResult.verified===false?" · "+strings.t("unverified"):"");color:SteelSeries.SteelSeriesService.operationResult.ok===false?Commons.Color.urgent:root.foreground;font.pixelSize:Style.font.body}
                    Text {width:parent.width;wrapMode:Text.WordWrap;textFormat:Text.PlainText;text:strings.t("hint");color:Qt.alpha(root.foreground,0.6);font.pixelSize:Style.font.body}
                }
            }
        }
    }
}
