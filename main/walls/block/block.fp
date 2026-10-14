#version 140

in mediump vec2 var_texcoord0;
// локальная координата Y вершины (mesh блока: -50..50)
in highp float var_local_y;

out vec4 out_fragColor;

uniform fs_uniforms
{
    // множитель цвета спрайта: xyz — RGB, w — непрозрачность (1 = сплошная)
    mediump vec4 tint;
    // срез кладки: x — сколько рядов снизу уже разбито, y — всего рядов
    mediump vec4 brick_break;
};

uniform mediump sampler2D texture_sampler;

void main()
{
    // разбитые снизу ряды кладки исчезают: фрагменты ниже среза отбрасываются.
    // локальный Y кладки: -50 (низ) .. +50 (верх)
    highp float t_rows = max(brick_break.y, 1.0);
    highp float cut = (brick_break.x / t_rows) * 100.0 - 50.0;
    if (var_local_y < cut)
    {
        discard;
    }
    mediump vec4 t = texture(texture_sampler, var_texcoord0.xy);
    out_fragColor = t * vec4(tint.xyz * tint.w, tint.w);
}
