import QtQuick
import QtQuick.Controls as Controls
import qs.Commons
Item {
    id: root
    property string label: ""
    property int minimum: 0
    property int maximum: 100
    property int step: 1
    property alias value: spin.value
    signal edited(int newValue)
    implicitHeight: Math.max(caption.implicitHeight,spin.implicitHeight)
    Text {id:caption;anchors.left:parent.left;anchors.verticalCenter:parent.verticalCenter;width:parent.width-spin.width-12;wrapMode:Text.WordWrap;textFormat:Text.PlainText;text:root.label;color:Color.foreground;font.family:Style.font.family;font.pixelSize:Style.font.body}
    Controls.SpinBox {id:spin;anchors.right:parent.right;from:root.minimum;to:root.maximum;stepSize:root.step;editable:true;onValueModified:root.edited(value)}
}
