"""Draw opt-in vegetation silhouettes in the native #717 battle movie."""

from battle_ui_hit_flash import function, method, var


CLEAR = 'ProjectFoliage.clear'
POLYGON = 'ProjectFoliage.polygon'
MAX_VERTICES = 16


def sources():
    clip = var('foliageMC')
    clear = function('_projectFoliageClear', ['shown'], [
        method(clip, 'clear'),
        ('set', clip, '_visible', var('shown')),
    ])
    coordinates = [name for index in range(MAX_VERTICES) for name in ('x%d' % index, 'y%d' % index)]
    count = var('count')
    path = [
        ('if', ('<', count, 3), [('return', None)]),
        ('if', ('<', MAX_VERTICES, count), [('return', None)]),
        method(clip, 'lineStyle', 1, var('colour'), 70),
        method(clip, 'beginFill', var('colour'), var('alpha')),
        method(clip, 'moveTo', var('x0'), var('y0')),
    ]
    for index in range(1, MAX_VERTICES):
        path.append(('if', ('<', index, count), [
            method(clip, 'lineTo', var('x%d' % index), var('y%d' % index)),
        ]))
    path += [method(clip, 'lineTo', var('x0'), var('y0')), method(clip, 'endFill')]
    # Flat fixed argument list keeps the call compatible with the native GameDelegate.
    return clear + function('_projectFoliagePolygon', ['colour', 'alpha', 'count'] + coordinates, path)


def setup(delegate, depth):
    return [
        ('assign', 'foliageMC', ('call', var('this'), 'createEmptyMovieClip', ['projectFoliage', depth])),
        ('set', var('foliageMC'), '_visible', False),
        ('do', ('call', delegate, 'addCallBack', [CLEAR, var('this'), '_projectFoliageClear'])),
        ('do', ('call', delegate, 'addCallBack', [POLYGON, var('this'), '_projectFoliagePolygon'])),
    ]
