(ns app.util.url)

(defn query-param
  "Read a query-string parameter from the current URL at call time, or nil.
   Call during component setup (form-2 outer let), not inside the render
   fn — the URL may have changed by the time a re-render runs."
  [k]
  (let [params (js/URLSearchParams. (.. js/window -location -search))]
    (.get params k)))
