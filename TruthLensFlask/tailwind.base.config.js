// base.html과 이를 상속하는 페이지용 설정.
// 테마는 이전 base.html 인라인 tailwind.config에서 그대로 옮긴 값이다(tools/tailwind.base.json).
const fs = require('fs');
const path = require('path');
const theme = require('./tools/tailwind.base.json');

// login.html은 fontSize 정의가 없는 별도 설정을 쓰므로 이 빌드에서 제외한다.
const templates = fs
  .readdirSync(path.join(__dirname, 'templates'))
  .filter((f) => f.endsWith('.html') && f !== 'login.html')
  .map((f) => `./templates/${f}`);

module.exports = {
  content: [...templates, './static/js/**/*.js'],
  darkMode: theme.darkMode,
  theme: theme.theme,
  plugins: [require('@tailwindcss/forms'), require('@tailwindcss/container-queries')],
};
