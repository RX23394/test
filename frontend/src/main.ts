import { createApp } from "vue";
import ElementPlus from "element-plus";
import "element-plus/dist/index.css";

import App from "./App.vue";
import { setUnauthorizedHandler } from "./api/api";
import router from "./router";
import "./assets/main.css";
import { pinia } from "./stores";
import { initializeTheme } from "./utils/theme";

const app = createApp(App);

initializeTheme();

setUnauthorizedHandler(async () => {
  if (router.currentRoute.value.name === "login") {
    return;
  }
  await router.replace({
    name: "login",
    query: { redirect: router.currentRoute.value.fullPath },
  });
});

app.use(pinia);
app.use(router);
app.use(ElementPlus);
app.mount("#app");
