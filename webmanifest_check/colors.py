"""Is this string a valid CSS colour? (syntax check, not a full CSS parser)"""

import re

NAMED = set("""aliceblue antiquewhite aqua aquamarine azure beige bisque black blanchedalmond blue blueviolet
brown burlywood cadetblue chartreuse chocolate coral cornflowerblue cornsilk crimson cyan darkblue darkcyan
darkgoldenrod darkgray darkgreen darkgrey darkkhaki darkmagenta darkolivegreen darkorange darkorchid darkred
darksalmon darkseagreen darkslateblue darkslategray darkslategrey darkturquoise darkviolet deeppink deepskyblue
dimgray dimgrey dodgerblue firebrick floralwhite forestgreen fuchsia gainsboro ghostwhite gold goldenrod gray
green greenyellow grey honeydew hotpink indianred indigo ivory khaki lavender lavenderblush lawngreen
lemonchiffon lightblue lightcoral lightcyan lightgoldenrodyellow lightgray lightgreen lightgrey lightpink
lightsalmon lightseagreen lightskyblue lightslategray lightslategrey lightsteelblue lightyellow lime limegreen
linen magenta maroon mediumaquamarine mediumblue mediumorchid mediumpurple mediumseagreen mediumslateblue
mediumspringgreen mediumturquoise mediumvioletred midnightblue mintcream mistyrose moccasin navajowhite navy
oldlace olive olivedrab orange orangered orchid palegoldenrod palegreen paleturquoise palevioletred papayawhip
peachpuff peru pink plum powderblue purple rebeccapurple red rosybrown royalblue saddlebrown salmon sandybrown
seagreen seashell sienna silver skyblue slateblue slategray slategrey snow springgreen steelblue tan teal
thistle tomato turquoise violet wheat white whitesmoke yellow yellowgreen transparent""".split())

_HEX = re.compile(r"^#(?:[0-9a-f]{3}|[0-9a-f]{4}|[0-9a-f]{6}|[0-9a-f]{8})$", re.I)
_NUM = r"[+-]?(?:\d+\.?\d*|\.\d+)(?:e[+-]?\d+)?"
_ARG = rf"(?:{_NUM}(?:%|deg|grad|rad|turn)?|none)"
_FUNC = re.compile(
    rf"^(?:rgb|rgba|hsl|hsla|hwb|lab|lch|oklab|oklch)\(\s*{_ARG}(?:\s*[, ]\s*{_ARG}){{2}}"
    rf"(?:\s*[,/]\s*{_ARG})?\s*\)$",
    re.I,
)
_COLOR_FN = re.compile(rf"^color\(\s*[a-z0-9-]+(?:\s+{_ARG}){{3}}(?:\s*/\s*{_ARG})?\s*\)$", re.I)


def is_css_color(value: str) -> bool:
    v = value.strip()
    if not v:
        return False
    return bool(_HEX.match(v) or v.lower() in NAMED or _FUNC.match(v) or _COLOR_FN.match(v))
