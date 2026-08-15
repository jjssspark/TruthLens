// login.html 전용 설정.
// base와 달리 fontSize가 정의돼 있지 않다. 이는 오타가 아니라 현재 배포본의 실제 상태이며,
// 합쳐서 빌드하면 죽어 있던 text-body-sm 등 25곳이 살아나 글자 크기가 바뀐다. 그래서 분리한다.
const theme = require('./tools/tailwind.login.json');

module.exports = {
  content: ['./templates/login.html'],
  darkMode: theme.darkMode,
  theme: theme.theme,
  plugins: [require('@tailwindcss/forms'), require('@tailwindcss/container-queries')],
};
