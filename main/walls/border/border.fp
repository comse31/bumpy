#version 140

in mediump vec2 var_texcoord0;

out vec4 out_fragColor;

uniform fs_uniforms
{
    // множитель цвета стекла: xyz — RGB, w — непрозрачность (1 = сплошная)
    mediump vec4 tint;
};

uniform mediump sampler2D texture_sampler;

void main()
{
    mediump vec4 t = texture(texture_sampler, var_texcoord0.xy);
    out_fragColor = t * vec4(tint.xyz * tint.w, tint.w);
}
