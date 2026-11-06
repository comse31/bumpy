#version 140

in mediump vec2 var_texcoord0;
// локальная координата Y вершины (mesh блока: -50..62.5)
in highp float var_local_y;

out vec4 out_fragColor;

uniform fs_uniforms
{
    // множитель цвета спрайта: xyz — RGB, w — непрозрачность (1 = сплошная)
    mediump vec4 tint;
    // срез кладки: x — локальный Y среза (граница ряда, считается в
    // block.script по таблице реальных швов текстуры)
    mediump vec4 brick_break;
};

uniform mediump sampler2D texture_sampler;

void main()
{
    // разбитые снизу ряды кладки исчезают: фрагменты ниже среза отбрасываются.
    // локальный Y кладки: -50 (низ) .. +62.5 (верх); границу ряда задаёт
    // block.script таблицей реальных швов block.png (ряды нарисованы
    // неравномерно, равномерная сетка резала бы кирпичи)
    if (var_local_y < brick_break.x)
    {
        discard;
    }
    mediump vec4 t = texture(texture_sampler, var_texcoord0.xy);
    out_fragColor = t * vec4(tint.xyz * tint.w, tint.w);
}
