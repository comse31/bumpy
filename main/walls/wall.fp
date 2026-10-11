#version 140

in mediump vec2 var_texcoord0;

out vec4 out_fragColor;

uniform fs_uniforms
{
    // цвет перегородки: xyz — RGB, w — непрозрачность (1 = сплошная)
    mediump vec4 tint;
};

void main()
{
    out_fragColor = vec4(tint.xyz * tint.w, tint.w);
}
