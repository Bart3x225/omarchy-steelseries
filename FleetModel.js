function safeText(value) { return String(value || '').slice(0,180).replace(/</g,'‹').replace(/>/g,'›').replace(/&/g,'＆'); }
function deviceLabel(d) {
    if (!d.wireless && !d.battery_supported) return '';
    return d.state === 'connected' && Number.isInteger(d.battery) && d.battery >= 0 && d.battery <= 100 ? d.battery+'%' : '—';
}
function advance(previous, devices, options) {
    var cfg=Object.assign({lowThreshold:20,criticalThreshold:5,notifyLow:true,notifyCritical:false,notifyFull:false,notifyConnections:true,confirmations:1},options||{});
    var known=Object.assign({},previous?previous.devices:{}), stable=Object.assign({},previous?previous.stable:{}), pending=Object.assign({},previous?previous.pending:{});
    var low=Object.assign({},previous?previous.low:{}), critical=Object.assign({},previous?previous.critical:{}), full=Object.assign({},previous?previous.full:{});
    var seen={},events=[];
    devices.forEach(function(d) { seen[d.id]=d; });
    var ids=Object.keys(known);Object.keys(seen).forEach(function(id){if(ids.indexOf(id)<0)ids.push(id);});
    ids.forEach(function(id) {
        var d=seen[id]||known[id],before=known[id];
        var observed=seen[id]?d.state:(cfg.inventoryComplete===false?'error':'offline');
        if(observed!=='connected'&&observed!=='offline')observed='error';
        if(!previous) stable[id]=observed==='error'?'unknown':observed;
        else if(observed==='error') delete pending[id];
        else if(observed!==stable[id]) {
            var p=pending[id];p=p&&p.state===observed?{state:observed,count:p.count+1}:{state:observed,count:1};pending[id]=p;
            if(p.count>=cfg.confirmations) {
                if(d.wireless&&cfg.notifyConnections&&(observed==='connected'||stable[id]==='connected')) events.push({type:observed==='connected'?'connected':'disconnected',device:d});
                stable[id]=observed;delete pending[id];
            }
        } else delete pending[id];
        if(seen[id]) {
            if(d.battery>cfg.lowThreshold||d.charging) delete low[id];
            if(d.battery>cfg.criticalThreshold||d.charging) delete critical[id];
            if(d.battery<100||!d.charging) delete full[id];
            if(d.state==='connected'&&d.wireless&&Number.isInteger(d.battery)&&d.battery>=0&&d.battery<=100) {
                if(!d.charging&&d.battery<=cfg.criticalThreshold&&cfg.notifyCritical&&!critical[id]) {
                    critical[id]=true;low[id]=true;events.push({type:'critical',device:d});
                } else if(!d.charging&&d.battery<=cfg.lowThreshold&&cfg.notifyLow&&!low[id]) { low[id]=true;events.push({type:'low',device:d}); }
                if(d.battery===100&&d.charging&&cfg.notifyFull&&!full[id]) {
                    if(before&&before.state==='connected'&&(before.battery<100||!before.charging)) events.push({type:'full',device:d});
                    full[id]=true;
                }
            }
            known[id]=d;
        }
    });
    return {devices:known,stable:stable,pending:pending,low:low,critical:critical,full:full,events:events};
}
