// Shared by the server layout (inline script) and the client theme hook, so it has no
// "use client" directive.

export const THEME_KEY = "preflight.theme";
export const THEME_QUERY = "(prefers-color-scheme: dark)";
/** sessionStorage: "seen" once the landing intro has been passed or skipped this session. */
export const INTRO_KEY = "preflight.intro";

/** Runs in <head> before the first paint, so the page never flashes the wrong theme (or an
 * intro the visitor has already passed this session). */
export const THEME_SCRIPT = `(function(){var t;try{t=localStorage.getItem("${THEME_KEY}");}catch(e){}if(t!=="light"&&t!=="dark"){t=window.matchMedia("${THEME_QUERY}").matches?"dark":"light";}document.documentElement.dataset.theme=t;try{if(sessionStorage.getItem("${INTRO_KEY}")==="seen")document.documentElement.dataset.intro="seen";}catch(e){}})();`;
