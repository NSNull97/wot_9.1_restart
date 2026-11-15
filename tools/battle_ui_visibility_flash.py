"""AS2 operator-only screen-space ray overlay in the native #717 battle movie."""
from battle_ui_hit_flash import function, method, var

CLEAR = 'ProjectVisibility.clear'
LINE = 'ProjectVisibility.line'
PANEL = 'ProjectVisibility.panel'
MARKER = 'ProjectVisibility.marker'
LAMP = 'ProjectVisibility.lamp'
NATIVE_LAMP = 'sixthSenseIndicator.show'
ROWS = 8


def sources():
    mc = var('visibilityMC')
    clear = function('_projectVisibilityClear', ['shown'], [method(mc,'clear'), ('set',mc,'_visible',var('shown'))])
    line = function('_projectVisibilityLine', ['x1','y1','x2','y2','colour'], [
        method(mc,'lineStyle',2,var('colour'),90), method(mc,'moveTo',var('x1'),var('y1')),
        method(mc,'lineTo',var('x2'),var('y2'))])
    names = ['line%d' % i for i in range(ROWS)]
    text = [('do',('fn','_projectFeedField',[mc,'visibilityText%d' % i,100+i,12,230+i*18,800,13,
                 0xffffff,'left',var(name),False,100])) for i,name in enumerate(names)]
    panel = function('_projectVisibilityPanel',names,text)
    marker = function('_projectVisibilityMarker', ['slot','x','y','text','colour'], [
        ('do',('fn','_projectFeedField',[mc,('+','visibilityMarker',var('slot')),('+',200,var('slot')),
                 var('x'),var('y'),256,12,var('colour'),'left',var('text'),False,100]))])
    indicator = var('sixthSenseIndicator')
    timer = var('sixthSenseStart')
    mode = var('projectVisibilityLampMode')
    # The original active sequence stops on its lit frame once the fade timer is cancelled.
    lamp = function('_projectVisibilityLamp', ['mode'], [
        ('assign', 'projectVisibilityLampMode', var('mode')),
        ('if', ('<', -1, timer), [('do', ('fn', 'clearInterval', [timer])),
                                  ('assign', 'sixthSenseStart', -1)]),
        ('if', ('==', mode, 'spotted'), [method(indicator, 'gotoAndPlay', 'active'), ('return', None)]),
        method(indicator, 'gotoAndStop', 'inactive')])
    # Preserve the underlying native function and route its visual calls when diagnostics are inactive.
    native_lamp = function('_projectVisibilityNativeLamp', ['shown'], [
        ('if', ('==', mode, 'native'), [('do', ('fn', 'onShowSixthSense', [var('shown')]))])])
    return clear + line + panel + marker + lamp + native_lamp


def setup(delegate, depth):
    return [('assign','visibilityMC',('call',var('this'),'createEmptyMovieClip',['projectVisibility',depth])),
            ('set',var('visibilityMC'),'_visible',False),
            ('assign', 'projectVisibilityLampMode', 'native'),
            ('do',('call',delegate,'addCallBack',[CLEAR,var('this'),'_projectVisibilityClear'])),
            ('do',('call',delegate,'addCallBack',[LINE,var('this'),'_projectVisibilityLine'])),
            ('do',('call',delegate,'addCallBack',[PANEL,var('this'),'_projectVisibilityPanel'])),
            ('do',('call',delegate,'addCallBack',[MARKER,var('this'),'_projectVisibilityMarker'])),
            ('do',('call',delegate,'addCallBack',[LAMP,var('this'),'_projectVisibilityLamp'])),
            ('do',('call',delegate,'addCallBack',[NATIVE_LAMP,var('this'),'_projectVisibilityNativeLamp']))]
