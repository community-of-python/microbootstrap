import {defaultTheme} from "@vuepress/theme-default";
import {defineUserConfig} from "vuepress/cli";
import {viteBundler} from "@vuepress/bundler-vite";

export default defineUserConfig({
  lang: "en-US",

  title: "VuePress",
  description: "My first VuePress Site",
  base: "/microbootstrap/",

  theme: defaultTheme({
    repo: "community-of-python/microbootstrap",
    repoLabel: "GitHub",
    repoDisplay: true,
    hostname: "https://community-of-python.github.io/",

    logo: "https://vuejs.press/images/hero.png",

    navbar: ["/", "/get-started"],
  }),

  bundler: viteBundler({
    viteOptions: {
      base: "https://community-of-python.github.io/assets/microbootstrap/",
    },
  }),
});
