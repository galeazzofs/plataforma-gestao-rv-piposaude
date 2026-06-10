(ns app.util.url)

(defn query-param
  "Read a query-string parameter from the current URL, or nil."
  [k]
  (let [params (js/URLSearchParams. (.. js/window -location -search))]
    (.get params k)))
