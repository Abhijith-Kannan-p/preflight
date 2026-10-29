// Shared by the server layout (inline script) and the client theme hook, so it has no
// "use client" directive.

export const THEME_KEY = "preflight.theme";
export const THEME_QUERY = "(prefers-color-scheme: dark)";

/** Runs in <head> before the first paint, so the page never flashes the wrong theme. */
export const THEME_SCRIPT = `(function(){var t;try{t=localStorage.getItem("${THEME_KEY}");}catch(e){}if(t!=="light"&&t!=="dark"){t=window.matchMedia("${THEME_QUERY}").matches?"dark":"light";}document.documentElement.dataset.theme=t;})();`;
