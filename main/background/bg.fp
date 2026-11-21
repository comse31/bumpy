#version 140

in mediump vec2 var_texcoord0;

out vec4 out_fragColor;

uniform fs_uniforms
{
    mediump vec4 tint;
};

uniform mediump sampler2D texture_sampler;

// Фоны нарисованы приглушённо, поэтому осветляем их.
// Гамма-коррекция вместо простого умножения: она поднимает средние тона
// (визуально +50% яркости), но не выбивает светлые участки в чистый белый,
// поэтому облака и градиенты неба сохраняют детали.
const mediump float BG_GAMMA = 1.5;

void main()
{
    mediump vec4 t = texture(texture_sampler, var_texcoord0.xy);
    t.rgb = pow(t.rgb, vec3(1.0 / BG_GAMMA));
    out_fragColor = t * vec4(tint.xyz * tint.w, tint.w);
}
