// Tailwind CLI의 --minify는 cssnano 기본 프리셋을 쓰는데, colormin이 rgba()를 hsla()로 바꾼다.
// 이 왕복 변환에서 채널당 1씩 어긋나 테두리 색이 미세하게 달라졌다. colormin만 끄고 나머지 압축은 유지한다.
module.exports = {
  plugins: {
    cssnano: {
      preset: ['default', { colormin: false }],
    },
  },
};
