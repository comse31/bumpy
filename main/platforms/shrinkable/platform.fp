#version 140

in mediump vec2 var_texcoord0;

out vec4 out_fragColor;

uniform fs_uniforms
{
    mediump vec4 tint;
};

uniform mediump sampler2D texture_sampler;

void main()
{
    // Расходуемая платформа: изображение 960x151 рисуется как есть, без SDF-обрезки
    // под игровой бокс 960x80 — форма целиком берётся из текстуры,
    // поэтому свисающие лианы за пределами бокса не отсекаются.
    mediump vec4 tint_pm = vec4(tint.xyz * tint.w, tint.w);
    out_fragColor = texture(texture_sampler, var_texcoord0.xy) * tint_pm;
}
