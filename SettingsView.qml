import QtQuick
import QtQuick.Controls as Controls
import qs.Commons
import qs.Commons as Commons
import qs.Ui
import "." as SteelSeries
import "FleetModel.js" as Model
Item {
    id: root
    property var draft: ({})
    implicitHeight: column.implicitHeight
    Commons.Translations {id:strings;directory:Qt.resolvedUrl("i18n")}
    function reset(){draft=JSON.parse(JSON.stringify(SteelSeries.SteelSeriesService.config))}
    function set(key,value){var copy=Object.assign({},draft);copy[key]=value;draft=copy}
    Component.onCompleted:reset()
    onVisibleChanged:if(visible)reset()
    Column {
        id:column;width:parent.width;spacing:Style.space(10)
        SteelSeries.FormSpin {width:parent.width;label:strings.t("pollSeconds");minimum:2;maximum:300;value:Number(root.draft.pollSeconds||5);onEdited:function(v){root.set("pollSeconds",v)}}
        SteelSeries.FormSpin {width:parent.width;label:strings.t("lowThreshold");minimum:1;maximum:99;value:Number(root.draft.lowThreshold||20);onEdited:function(v){root.set("lowThreshold",v)}}
        SteelSeries.FormSpin {width:parent.width;label:strings.t("criticalThreshold");minimum:0;maximum:Math.max(0,Number(root.draft.lowThreshold||20));value:Number(root.draft.criticalThreshold||0);onEdited:function(v){root.set("criticalThreshold",v)}}
        Repeater {
            model:["notifyLow","notifyCritical","notifyFull","notifyConnections","experimentalControls"]
            delegate:Controls.CheckBox {
                required property string modelData
                width:column.width;text:strings.t(modelData);checked:!!root.draft[modelData]
                onToggled:root.set(modelData,checked)
            }
        }
        Text {width:parent.width;wrapMode:Text.WordWrap;textFormat:Text.PlainText;text:strings.t("debounceHint");color:Color.foreground;font.pixelSize:Style.font.body}
        Text {textFormat:Text.PlainText;text:strings.t("visibleDevices");color:Color.foreground;font.pixelSize:Style.font.body}
        Repeater {
            model:SteelSeries.SteelSeriesService.snapshot.devices||[]
            delegate:Controls.CheckBox {
                required property var modelData
                width:column.width;text:Model.safeText(modelData.name)
                checked:(root.draft.hiddenIds||[]).indexOf(modelData.id)<0
                onToggled:{var ids=(root.draft.hiddenIds||[]).slice();var at=ids.indexOf(modelData.id);if(checked&&at>=0)ids.splice(at,1);else if(!checked&&at<0)ids.push(modelData.id);root.set("hiddenIds",ids)}
            }
        }
        Text {width:parent.width;wrapMode:Text.WordWrap;textFormat:Text.PlainText;text:strings.t("historyRetention");color:Color.foreground;font.pixelSize:Style.font.body}
        WidgetButton {width:parent.width;text:strings.t("saveSettings");interactive:!SteelSeries.SteelSeriesService.busy;onPressed:SteelSeries.SteelSeriesService.saveConfig(root.draft)}
    }
}
