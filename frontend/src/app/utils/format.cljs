(ns app.utils.format
  "Shared formatting helpers. Extract anything that more than two views
   reimplement; keep ad-hoc, view-specific formatters in their own ns.")

(defn- ->number
  "Coerce v to a JS number, parsing strings. Returns nil for nil, empty, or
   non-parseable inputs."
  [v]
  (when (some? v)
    (let [n (if (string? v) (js/parseFloat v) v)]
      (when-not (js/isNaN n) n))))

(defn fmt-brl
  "Format a numeric value as Brazilian Real with two decimals — e.g. 1234.5 -> \"R$ 1.234,50\".
   Accepts a number or a string parseable as float. Returns nil for nil or NaN input."
  [v]
  (when-let [n (->number v)]
    (str "R$ " (.toLocaleString n "pt-BR"
                                #js {:minimumFractionDigits 2
                                     :maximumFractionDigits 2}))))

(defn fmt-brl-int
  "Format a numeric value as Brazilian Real, rounded, no decimals — e.g. 1234.5 -> \"R$ 1.234\".
   Accepts a number or a string parseable as float. Returns nil for nil or NaN input."
  [v]
  (when-let [n (->number v)]
    (str "R$ " (.toLocaleString (js/Math.round n) "pt-BR"))))

(defn int-brl
  "Format a numeric value as a pt-BR integer with no currency prefix — e.g. 1234.5 -> \"1.234\".
   Use when the surrounding markup already provides the currency symbol.
   Accepts a number or a string parseable as float. Returns nil for nil or NaN input."
  [v]
  (when-let [n (->number v)]
    (.toLocaleString (js/Math.round n) "pt-BR")))
