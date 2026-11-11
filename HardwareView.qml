import QtQuick
import QtQuick.Controls as Controls
import qs.Commons
import qs.Commons as Commons
import qs.Ui
import "." as SteelSeries
Item {
    id:root
    property var device: ({})
    property string identity: String(device.id||"")
    property var draft: ({})
    readonly property var descriptors: device.controls||[]
    implicitHeight:column.implicitHeight
    Commons.Translations {id:strings;directory:Qt.resolvedUrl("i18n")}
    onIdentityChanged:draft=({})
    function set(key,value){var copy=Object.assign({},draft);copy[key]=value;draft=copy}
    Column {
        id:column;width:parent.width;spacing:Style.space(12)
        Text {width:parent.width;wrapMode:Text.WordWrap;textFormat:Text.PlainText;text:!SteelSeries.SteelSeriesService.config.experimentalControls?strings.t("controlsOptInHint"):root.descriptors.length?strings.t("hardwareHint"):strings.t("noControls");color:Color.foreground;font.pixelSize:Style.font.body}
        Repeater {
            model:root.descriptors
            delegate:Column {
                id:field
                required property var modelData
                width:column.width;spacing:Style.space(6)
                Text {width:parent.width;wrapMode:Text.WordWrap;textFormat:Text.PlainText;text:strings.t("control."+field.modelData.key)!=="control."+field.modelData.key?strings.t("control."+field.modelData.key):String(field.modelData.label);color:Color.foreground;font.pixelSize:Style.font.body}
                Controls.SpinBox {
                    visible:field.modelData.type==="int"
                    from:Number(field.modelData.min||0);to:Number(field.modelData.max||100);stepSize:Number(field.modelData.step||1);editable:true
                    value:root.draft[field.modelData.key]===undefined?from:Number(root.draft[field.modelData.key])
                    onValueModified:root.set(field.modelData.key,value)
                }
                Controls.ComboBox {
                    visible:field.modelData.type==="choice"
                    width:parent.width
                    model:field.modelData.choices||[];textRole:"label";valueRole:"value"
                    currentIndex:root.draft[field.modelData.key]===undefined?-1:indexOfValue(root.draft[field.modelData.key])
                    onActivated:root.set(field.modelData.key,currentValue)
                }
            }
        }
        Text {visible:Object.keys(root.draft).length>0;width:parent.width;wrapMode:Text.WrapAnywhere;textFormat:Text.PlainText;text:strings.t("pending")+" "+JSON.stringify(root.draft);color:Color.foreground;font.pixelSize:Style.font.body}
        WidgetButton {visible:root.descriptors.length>0;width:parent.width;text:strings.t("apply");interactive:Object.keys(root.draft).length>0&&!SteelSeries.SteelSeriesService.busy&&root.device.state==="connected";onPressed:SteelSeries.SteelSeriesService.applyDevice(root.device.id,root.draft)}
        Text {width:parent.width;wrapMode:Text.WordWrap;textFormat:Text.PlainText;text:strings.t("rgbExternal");color:Qt.alpha(Color.foreground,0.6);font.pixelSize:Style.font.body}
    }
}
