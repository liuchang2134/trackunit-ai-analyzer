/* Shared chart palette for the dark industrial console.
   ECharts defaults assume a light page background, so every chart states these
   explicitly instead of relying on axis and slider defaults that would render
   invisible labels or a bright white band against the dark surface. */
const chartTheme = {
  ink:'#e8eff8', inkSecondary:'#b3c2d4', muted:'#8b9cb0',
  line:'#24303d', lineStrong:'#33414f',
  surface1:'#111820', surface2:'#161f2a', surface3:'#1d2733',
  brand:'#0055d9', accent:'#38c8d8', warn:'#e0a33f', ok:'#4ecb8d',
  axisLine:'#33414f', splitLine:'#1f2a36'
};
function chartAxisText(size=11) {
  return {color:chartTheme.muted,fontSize:size};
}
function chartTooltip(extra={}) {
  return Object.assign({backgroundColor:'#111820',borderColor:chartTheme.lineStrong,
    textStyle:{color:chartTheme.ink,fontSize:12}},extra);
}
function chartSlider() {
  return {type:'slider',bottom:8,height:22,filterMode:'none',borderColor:chartTheme.lineStrong,
    backgroundColor:'#0e141b',fillerColor:'#0055d933',
    handleStyle:{color:'#38c8d8',borderColor:'#38c8d8'},
    moveHandleStyle:{color:'#33414f'},
    dataBackground:{lineStyle:{color:chartTheme.lineStrong},areaStyle:{color:'#1d2733'}},
    selectedDataBackground:{lineStyle:{color:chartTheme.accent},areaStyle:{color:'#0055d944'}},
    textStyle:{color:chartTheme.muted,fontSize:10}};
}
