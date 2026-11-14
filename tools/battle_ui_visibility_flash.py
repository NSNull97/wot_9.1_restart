"""AS2 operator-only screen-space ray overlay in the native #717 battle movie."""
from battle_ui_hit_flash import function, method, var

CLEAR = 'ProjectVisibility.clear'
LINE = 'ProjectVisibility.line'
PANEL = 'ProjectVisibility.panel'
MARKER = 'ProjectVisibility.marker'
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
    return clear + line + panel + marker


def setup(delegate, depth):
    return [('assign','visibilityMC',('call',var('this'),'createEmptyMovieClip',['projectVisibility',depth])),
            ('set',var('visibilityMC'),'_visible',False),
            ('do',('call',delegate,'addCallBack',[CLEAR,var('this'),'_projectVisibilityClear'])),
            ('do',('call',delegate,'addCallBack',[LINE,var('this'),'_projectVisibilityLine'])),
            ('do',('call',delegate,'addCallBack',[PANEL,var('this'),'_projectVisibilityPanel'])),
            ('do',('call',delegate,'addCallBack',[MARKER,var('this'),'_projectVisibilityMarker']))]
