#version 140

in mediump vec2 var_texcoord0;
// локальные координаты вершины после shrink, до bend — для скругления углов:
// интерполяция varying по сжатому quad'у автоматически «следует» за shrink
in highp vec2 var_local_pos;
// масштабы по локальным осям X и Y (длины столбцов мировой матрицы)
in highp vec2 var_scale;
// коэффициент уменьшения платформы (shrinkable), может быть отрицательным при перелёте пружины
in highp float var_shrink;

out vec4 out_fragColor;

uniform fs_uniforms
{
    mediump vec4 tint;
    // x — радиус скругления углов платформы в мировых единицах (пикселях) (0 = квадратные)
    mediump vec4 corner_radius;
};

uniform mediump sampler2D texture_sampler;

void main()
{
    // переводим локальные координаты (после shrink, до bend) в мировые/пиксельные единицы,
    // чтобы радиус скругления был одинаковым по X и Y независимо от масштаба платформы
    highp vec2 p = var_local_pos * var_scale;
    highp float half_w = 480.0 * abs(var_shrink) * var_scale.x;
    highp float half_h = 40.0 * var_scale.y;
    highp float r = corner_radius.x;

    // SDF скруглённого прямоугольника (круглые углы радиуса r в пиксельном пространстве);
    // корректно вырождается в капсулу при r >= half_h и в обычный прямоугольник при r = 0
    highp vec2 q = abs(p) - vec2(half_w, half_h) + r;
    highp float d = length(max(q, 0.0)) + min(max(q.x, q.y), 0.0) - r;
    // пиксели за скруглённым контуром отбрасываем — форма не зависит от текстуры
    if (d > 0.0)
    {
        discard;
    }

    mediump vec4 tint_pm = vec4(tint.xyz * tint.w, tint.w);
    out_fragColor = texture(texture_sampler, var_texcoord0.xy) * tint_pm;
}
