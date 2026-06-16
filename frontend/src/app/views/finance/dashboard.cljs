(ns app.views.finance.dashboard
  (:require [clojure.string :as str]
            [reagent.core :as r]
            [re-frame.core :as rf]
            ["recharts" :refer [ResponsiveContainer AreaChart Area BarChart Bar
                                XAxis YAxis CartesianGrid Tooltip
                                ReferenceLine ReferenceArea]]
            [app.ds.layout :as layout]
            [app.auth.subs]
            [app.utils.format :as fmt]))

;; Recharts adapters (kept private to this view).
(def ^:private rc-responsive (r/adapt-react-class ResponsiveContainer))
(def ^:private rc-area-chart (r/adapt-react-class AreaChart))
(def ^:private rc-area (r/adapt-react-class Area))
(def ^:private rc-bar-chart (r/adapt-react-class BarChart))
(def ^:private rc-bar (r/adapt-react-class Bar))
(def ^:private rc-x-axis (r/adapt-react-class XAxis))
(def ^:private rc-y-axis (r/adapt-react-class YAxis))
(def ^:private rc-cartesian-grid (r/adapt-react-class CartesianGrid))
(def ^:private rc-tooltip (r/adapt-react-class Tooltip))
(def ^:private rc-reference-line (r/adapt-react-class ReferenceLine))
(def ^:private rc-reference-area (r/adapt-react-class ReferenceArea))

;; Finance dashboard — three editorial rows.
;; Row 1: Potencial a pagar · Comissão Paga · Obrigação aberta
;; Row 2: Comissão x Agenciamento (split numerics + 6-month trend)
;; Row 3: Fluxo de Caixa Projetado (30/60/90 horizons + chart)
;; Renders only data returned by the API; empty states stand in until the
;; backend has values to show.

(defn- ->num
  "Coerce strings/numbers to a JS number; nil/empty/NaN → nil."
  [v]
  (when (some? v)
    (let [n (if (string? v) (js/parseFloat v) v)]
      (when-not (or (nil? n) (js/isNaN n)) n))))

(defn- brl-value
  "STIX Two Text number with the R$ prefix in UI font (or fallback when nil)."
  [v fallback]
  (if (some? v)
    [:<> [:span.currency "R$"] (or (fmt/int-brl v) fallback)]
    fallback))

(defn- chart-empty [label]
  [:div {:style {:padding "32px" :text-align "center" :color "var(--fg-3)"
                 :font-family "var(--font-mono)" :font-size "12px"}}
   label])

(defn- period-suffix
  "Mono caption fragment for the active period, e.g. 'Q2 · 2026' or 'histórico'."
  [{:keys [year quarter]}]
  (let [year-label (if (and (string? year) (str/ends-with? year "_plus"))
                     (str (first (str/split year #"_")) "+")
                     (str year))]
    (cond
      (and (= :all year) (= :all quarter)) "histórico"
      (and (not= :all year) (= :all quarter)) year-label
      (and (= :all year) (not= :all quarter)) (str "Q" quarter)
      :else (str "Q" quarter " · " year-label))))

(defn- format-asof
  "Format an ISO timestamp into 'dd mmm yyyy, hh:mm' in lowercase pt-BR."
  [iso]
  (when (and iso (string? iso))
    (try
      (let [d (js/Date. iso)]
        (when-not (js/isNaN (.getTime d))
          (-> (.toLocaleString d "pt-BR"
                               #js {:day "2-digit" :month "short" :year "numeric"
                                    :hour "2-digit" :minute "2-digit"})
              (.toLowerCase)
              (.replace "." ""))))
      (catch :default _ nil))))

;; ----- pt-BR axis helpers ---------------------------------------------

(def ^:private pt-months
  ["jan" "fev" "mar" "abr" "mai" "jun"
   "jul" "ago" "set" "out" "nov" "dez"])

(defn- pt-month
  "1 → 'jan', 12 → 'dez'. Returns nil on out-of-range."
  [m]
  (when (and (number? m) (<= 1 m 12))
    (nth pt-months (dec m))))

(defn- ym-parts
  "'2026-05' → {:y 2026 :m 5 :q 2}. Returns nil on malformed input."
  [ym]
  (when (and (string? ym) (= 7 (count ym)))
    (let [y (js/parseInt (subs ym 0 4) 10)
          m (js/parseInt (subs ym 5 7) 10)]
      (when (and (not (js/isNaN y)) (not (js/isNaN m))
                 (<= 1 m 12))
        {:y y :m m :q (inc (quot (dec m) 3))}))))

(defn- parse-pt-label
  "Fallback parser for the 'mai/26' shape when :ym is absent.
   Returns {:y 26 :m 5} as integers (year is 2-digit only)."
  [s]
  (when (and (string? s) (re-find #"^[a-z]{3}/\d{2}$" s))
    (let [[mon yr] (str/split s #"/")
          midx (.indexOf pt-months mon)]
      (when (>= midx 0)
        {:y (+ 2000 (js/parseInt yr 10))
         :m (inc midx)
         :q (inc (quot midx 3))}))))

(defn- point-parts
  "Extracts {:y :m :q} from a series point, preferring :ym (full year)
   and falling back to the 'mai/26' label."
  [p]
  (or (ym-parts (:ym p)) (parse-pt-label (:label p))))

(defn- horizon-closing-month
  "'fecha jun/26' style label for the month landing N days from today.
   Used by the horizon strip to anchor each window to a real month."
  [days]
  (let [d (js/Date.)]
    (.setDate d (+ (.getDate d) days))
    (str (pt-month (inc (.getMonth d)))
         "/"
         (.padStart (str (mod (.getFullYear d) 100)) 2 "0"))))

;; ----- Row 1: KPI cards ------------------------------------------------
;; Potencial a pagar = A apurar + Projetado, valued at potencial contratual/12
;;   per remaining month of the 12-month commission clock (never raw NF).
;; Comissão Paga     = Σ policies.total_paid_comissao + total_paid_agenciamento.
;; Obrigação aberta  = non-realized monthly competencies in current filter.

(defn- kpi-potencial [{:keys [value caption]}]
  [:div.kpi
   [:div.kpi-label
    [layout/icon "target" {:width 14 :height 14}]
    "comissão a pagar projetada"]
   [:div.kpi-value (brl-value value "·")]
   [:div.kpi-foot
    [:span (or caption "a apurar + projetado · exclui realizado")]]
   [:svg.kpi-grafismo {:style {:color "var(--beige-light)"}}
    [:use {:href "#i-grafismo"}]]])

(defn- kpi-paga [{:keys [value caption]}]
  [:div.kpi
   [:div.kpi-label
    [layout/icon "check" {:width 14 :height 14}]
    "comissão paga"]
   [:div.kpi-value (brl-value value "·")]
   [:div.kpi-foot
    [:span (or caption "comissão + agenciamento · histórico")]]])

(defn- kpi-saldo [{:keys [value caption]}]
  [:div.kpi
   [:div.kpi-label
    [layout/icon "money" {:width 14 :height 14}]
    "obrigação aberta"]
   [:div.kpi-value (brl-value value "·")]
   [:div.kpi-foot
    [:span (or caption "competências não realizadas · até 12 meses")]]
   [:svg.kpi-grafismo {:style {:color "var(--neutral-light)"}}
    [:use {:href "#i-grafismo-listras"}]]])

;; ----- Shared chart helpers --------------------------------------------

(defn- fmt-axis-val
  "Compact Y-axis label: 0 → '0', 50000 → '50k', 1500000 → '1.5M'."
  [v]
  (cond
    (zero? v) "0"
    (>= v 1000000) (let [m (/ v 1000000)]
                     (if (== m (js/Math.round m))
                       (str (js/Math.round m) "M")
                       (str (.toFixed m 1) "M")))
    (>= v 1000)    (let [k (/ v 1000)]
                     (if (== k (js/Math.round k))
                       (str (js/Math.round k) "k")
                       (str (.toFixed k 1) "k")))
    :else (str (js/Math.round v))))

(defn- nice-y-ceil
  "Pick a tidy maximum for the y-axis based on the largest value in the set.
   Steps grow on a 1·2·5·10 scale so the last gridline sits on a round figure."
  [values]
  (let [raw-max (if (seq values) (reduce max values) 1)
        safe    (max 1 raw-max)
        mag     (js/Math.pow 10 (js/Math.floor (js/Math.log10 safe)))
        norm    (/ safe mag)
        step    (* mag (cond (<= norm 1.5) 0.5
                             (<= norm 3)   1
                             (<= norm 7)   2
                             :else          5))]
    (* step (js/Math.ceil (/ safe step)))))

(defn- reduced-motion?
  "True when the user asked for reduced motion. Recharts ignores the OS
   preference on its own, so we gate chart animation on it explicitly."
  []
  (boolean
   (and (exists? js/window)
        (.-matches (js/matchMedia "(prefers-reduced-motion: reduce)")))))

;; ----- Row 2: Comissão x Agenciamento ---------------------------------

(defn- proportion-strip [comissao agenciamento]
  (let [c (or (->num comissao) 0)
        a (or (->num agenciamento) 0)
        total (+ c a)
        com-pct (if (pos? total) (* 100 (/ c total)) 0)
        ag-pct  (if (pos? total) (* 100 (/ a total)) 0)]
    [:div.proportion-strip
     [:div.seg.primary {:style {:width (str com-pct "%")}}]
     [:div.seg.beige   {:style {:width (str ag-pct "%")}}]]))

(defn- comissao-chart-data
  "Backend points → dense Recharts rows. Each row carries comissão, agenciamento
   and their sum so a stacked bar can show both the monthly total (height) and
   its split, and the tooltip can read everything off a single row."
  [series]
  (->> series
       (map (fn [p]
              (let [c (->num (:comissao p))
                    a (->num (:agenciamento p))]
                {:label (:label p)
                 :comissao c
                 :agenciamento a
                 :total (+ (or c 0) (or a 0))})))
       vec))

(defn- comissao-tooltip-render
  "Dark editorial tooltip — month label on top, comissão + agenciamento rows
   with their dots, then a ruled total and the split percentage."
  [props]
  (let [p (js->clj props :keywordize-keys true)
        active? (:active p)
        row (some-> (:payload p) first :payload)
        row (cond-> row (and row (not (map? row)))
                    (js->clj :keywordize-keys true))]
    (when (and active? row)
      (let [c (or (->num (:comissao row)) 0)
            a (or (->num (:agenciamento row)) 0)
            total (+ c a)
            com-pct (when (pos? total) (* 100 (/ c total)))
            ag-pct  (when (pos? total) (* 100 (/ a total)))]
        (r/as-element
         [:div.comissao-tooltip
          [:span.lab (:label row)]
          [:div.comissao-tooltip-row
           [:span.k [:i.dot.-comissao] "comissão"]
           [:span.v (or (fmt/fmt-brl-int c) "R$ 0")]]
          [:div.comissao-tooltip-row
           [:span.k [:i.dot.-agenciamento] "agenciamento"]
           [:span.v (or (fmt/fmt-brl-int a) "R$ 0")]]
          [:div.comissao-tooltip-total
           [:span.k "total"]
           [:span.v (or (fmt/fmt-brl-int total) "R$ 0")]]
          (when (and com-pct ag-pct)
            [:div.comissao-tooltip-split
             (str (.toFixed com-pct 0) "% · " (.toFixed ag-pct 0) "%")])])))))

(def ^:private comissao-tooltip-content
  (r/reactify-component comissao-tooltip-render))

(defn- chart-comissao-agenciamento
  "Comissão vs agenciamento paid per month — Recharts stacked bars (ink base,
   beige cap). Bar height is the total paid that month; the split echoes the
   card's proportion strip across time. Responsive, animated, hover surfaces a
   dark editorial tooltip with both values, the total and the split."
  [series]
  (let [pts    (comissao-chart-data series)
        n      (count pts)
        totals (keep :total pts)]
    (if (or (zero? n) (not (some pos? totals)))
      [:div.series-fallback
       [:div.lab "histórico mensal"]
       [:strong "sem série mensal para este filtro"]
       [:span "os totais acima continuam válidos para o período selecionado"]]
      (let [y-ceil (nice-y-ceil totals)
            interval (cond (> n 10) 2 (> n 6) 1 :else 0)
            animate? (not (reduced-motion?))]
        [:div.comissao-recharts-frame
         {:role "img"
          :aria-label "Comissão e agenciamento pagos por competência mensal"}
         [rc-responsive {:width "100%" :height "100%"}
          [rc-bar-chart {:data (clj->js pts)
                         :margin #js {:top 16 :right 18 :bottom 8 :left 4}
                         :barCategoryGap "30%"}
           [rc-cartesian-grid {:stroke "var(--border-subtle)"
                               :strokeDasharray "2 5"
                               :vertical false}]
           [rc-x-axis {:dataKey "label"
                       :axisLine false
                       :tickLine false
                       :tickMargin 12
                       :interval interval
                       :tick #js {:fill "var(--fg-3)"
                                  :fontSize 11
                                  :fontFamily "Manrope, sans-serif"
                                  :letterSpacing "0.02em"}}]
           [rc-y-axis {:domain #js [0 y-ceil]
                       :tickFormatter fmt-axis-val
                       :axisLine false
                       :tickLine false
                       :width 52
                       :tickMargin 8
                       :tick #js {:fill "var(--fg-3)"
                                  :fontSize 11
                                  :fontFamily "Manrope, sans-serif"
                                  :letterSpacing "0.02em"}}]
           [rc-tooltip {:cursor #js {:fill "var(--fg-1)" :fillOpacity 0.05}
                        :content comissao-tooltip-content
                        :wrapperStyle #js {:outline "none"}}]
           [rc-bar {:dataKey "comissao"
                    :name "comissão"
                    :stackId "ca"
                    :fill "var(--black)"
                    :maxBarSize 46
                    :isAnimationActive animate?
                    :animationDuration 650
                    :animationEasing "ease-out"
                    :radius #js [0 0 0 0]}]
           [rc-bar {:dataKey "agenciamento"
                    :name "agenciamento"
                    :stackId "ca"
                    :fill "var(--beige-light)"
                    :maxBarSize 46
                    :isAnimationActive animate?
                    :animationDuration 650
                    :animationEasing "ease-out"
                    :radius #js [4 4 0 0]}]]]]))))

(defn- comissao-data-table
  "Tabular alternative to the comparison chart, disclosed on demand. Screen
   readers get the same numbers the bars encode; sighted users can expand it."
  [series]
  (let [rows (filter (fn [p] (or (->num (:comissao p)) (->num (:agenciamento p))))
                     series)]
    (when (seq rows)
      [:details.chart-data-table
       [:summary "Ver dados em tabela"]
       [:div.table-wrap
        [:table.table
         [:caption.sr-only
          "Comissão e agenciamento pagos por competência mensal, em reais."]
         [:thead
          [:tr
           [:th {:scope "col"} "Mês"]
           [:th.right {:scope "col"} "Comissão"]
           [:th.right {:scope "col"} "Agenciamento"]
           [:th.right {:scope "col"} "Total"]]]
         [:tbody
          (for [p rows
                :let [c (or (->num (:comissao p)) 0)
                      a (or (->num (:agenciamento p)) 0)]]
            ^{:key (:label p)}
            [:tr
             [:th {:scope "row"} (:label p)]
             [:td.right.num (or (fmt/fmt-brl-int (:comissao p)) "·")]
             [:td.right.num (or (fmt/fmt-brl-int (:agenciamento p)) "·")]
             [:td.right.num (fmt/fmt-brl-int (+ c a))]])]]]])))

(defn- comissao-agenciamento-card [{:keys [comissao agenciamento series period]}]
  (let [c (or (->num comissao) 0)
        a (or (->num agenciamento) 0)
        total (+ c a)
        com-pct (when (pos? total) (* 100 (/ c total)))
        ag-pct  (when (pos? total) (* 100 (/ a total)))]
    [:div.card.comissao-card
     [:div.card-head
      [:div [:h3 "Comissão x Agenciamento"]
       [:div.card-sub (or period "Liberado · últimos 6 meses")]]
      [:div.legend
       [:span.legend-dot {:style {"--dot" "var(--black)"}} "comissão"]
       [:span.legend-dot {:style {"--dot" "var(--beige-light)"}} "agenciamento"]]]
     [:div.split-numerics
      [:div.col
       [:div.lab "comissão"]
       [:div.num (brl-value comissao "·")]
       [:div.lab (if com-pct (str (.toFixed com-pct 1) "% do total") "—")]]
      [:div.rule]
      [:div.col
       [:div.lab "agenciamento"]
       [:div.num (brl-value agenciamento "·")]
       [:div.lab (if ag-pct (str (.toFixed ag-pct 1) "% do total") "—")]]]
     [proportion-strip comissao agenciamento]
     [:div.comissao-chart-frame
      [chart-comissao-agenciamento series]
      [comissao-data-table series]]]))

;; ----- Row 3: Fluxo de Caixa Projetado --------------------------------

(defn- trim-fluxo-series
  "Drop leading and trailing months that have no data on either series.
   Keeps the chart focused on the months that actually carry signal."
  [series]
  (let [has-data? (fn [p] (or (some? (->num (:realizado p)))
                              (some? (->num (:a_apurar p)))
                              (some? (->num (:projetado p)))))]
    (->> series
         (drop-while (complement has-data?))
         reverse
         (drop-while (complement has-data?))
         reverse
         vec)))

(defn- today-index
  "Index of the current calendar month. Returns nil when the filter hides it."
  [pts]
  (some (fn [[i p]] (when (:is_current_month p) i))
        (map-indexed vector pts)))

(defn- projected-points
  "Projected points after chart trimming, preserving the index used by the SVG."
  [series]
  (->> (trim-fluxo-series series)
       (map-indexed (fn [i p]
                      (when-let [v (->num (:projetado p))]
                        {:index i :point p :value v})))
       (keep identity)
       vec))

(defn- default-projected-index [series]
  (let [pts (trim-fluxo-series series)
        today-i (today-index pts)
        projected (projected-points series)]
    (or (when (and today-i (some #(= today-i (:index %)) projected))
          today-i)
        (:index (first projected)))))

(defn- fluxo-chart-data
  "Convert backend series to dense points keyed for Recharts. The numeric
   :idx anchors the x-axis so reference lines can sit at fractional positions
   (today's day-of-month inside the current month band)."
  [series]
  (->> (trim-fluxo-series series)
       (map-indexed
        (fn [i p]
          {:idx i
           :label (:label p)
           :ym (:ym p)
           :is_current_month (boolean (:is_current_month p))
           :projetado (->num (:projetado p))
           :a_apurar (->num (:a_apurar p))
           :realizado (->num (:realizado p))}))
       vec))

(defn- fluxo-tooltip-render
  "Dark editorial tooltip — month label in lowercase Manrope on top, projected
   value in STIX Two Text tabular-nums below."
  [props]
  (let [p (js->clj props :keywordize-keys true)
        active? (:active p)
        payload (first (:payload p))
        row (when payload (:payload payload))
        row (cond-> row (and row (not (map? row)))
                    (js->clj :keywordize-keys true))
        v (some-> row :projetado)]
    (when (and active? row (some? v))
      (r/as-element
       [:div.fluxo-tooltip
        [:span.lab (:label row)]
        [:strong (or (fmt/fmt-brl v) "R$ 0,00")]]))))

(def ^:private fluxo-tooltip-content
  (r/reactify-component fluxo-tooltip-render))

(defn- today-fraction-of-month
  "Returns the fraction (0..1) of the current month elapsed today, suitable
   for placing a 'today' marker between two month gridlines."
  []
  (let [d (js/Date.)
        day (.getDate d)
        last-day (.getDate (js/Date. (.getFullYear d) (inc (.getMonth d)) 0))]
    (max 0 (min 1 (/ (dec day) (max 1 (dec last-day)))))))

(defn- chart-fluxo-caixa
  "Forecast chart — projected receivables across the next 12 months.
   Built on Recharts: responsive AreaChart with a smooth monotone line, a
   soft blue gradient area, dashed gridlines, a beige reference band for
   the current month, and a dashed today rule. Hover surfaces a dark
   editorial pill with the month label and serif value."
  ([data] (chart-fluxo-caixa data nil))
  ([data {:keys [on-select]}]
   (let [pts (fluxo-chart-data data)
         n   (count pts)
         projected-values (keep :projetado pts)]
     (if (or (zero? n) (empty? projected-values))
       [chart-empty "Sem fluxo de caixa para o período"]
       (let [today-i  (some (fn [[i p]] (when (:is_current_month p) i))
                            (map-indexed vector pts))
             today-x  (when today-i (+ today-i (today-fraction-of-month)))
             band-x1  today-i
             band-x2  (when today-i (min (dec n) (inc today-i)))
             y-ceil   (nice-y-ceil projected-values)
             label-nth (cond (> n 14) 3 (> n 8) 2 :else 1)
             tick-idxs (vec (filter #(zero? (mod % label-nth)) (range n)))
             tick-labels (into {} (map (juxt :idx :label) pts))
             on-mouse-move (fn [^js state]
                             (when (and state on-select)
                               (let [active? (.-isTooltipActive state)
                                     idx (.-activeTooltipIndex state)]
                                 (when (and active? (number? idx))
                                   (on-select idx)))))]
         [:div.fluxo-recharts-frame
          {:role "img"
           :aria-label "Fluxo de caixa projetado por competência mensal"}
          [rc-responsive {:width "100%" :height "100%"}
           [rc-area-chart {:data (clj->js pts)
                           :margin #js {:top 28 :right 28 :bottom 12 :left 8}
                           :onMouseMove on-mouse-move}
            [:defs
             [:linearGradient {:id "fluxo-projetado-fill" :x1 "0" :y1 "0" :x2 "0" :y2 "1"}
              [:stop {:offset "0%" :stopColor "var(--blue-light)" :stopOpacity 0.55}]
              [:stop {:offset "55%" :stopColor "var(--blue-light)" :stopOpacity 0.14}]
              [:stop {:offset "100%" :stopColor "var(--blue-light)" :stopOpacity 0}]]]
            [rc-cartesian-grid {:stroke "var(--border-subtle)"
                                :strokeDasharray "2 5"
                                :vertical false}]
            (when (and (number? band-x1) (number? band-x2) (> band-x2 band-x1))
              [rc-reference-area {:x1 band-x1 :x2 band-x2
                                  :fill "var(--beige-lightest)"
                                  :fillOpacity 1
                                  :stroke "var(--beige-light)"
                                  :strokeOpacity 0.5
                                  :strokeDasharray "0"
                                  :ifOverflow "visible"
                                  :label #js {:value "mês atual"
                                              :position "insideTopLeft"
                                              :offset 10
                                              :fill "var(--fg-2)"
                                              :fontSize 10
                                              :fontFamily "Manrope, sans-serif"
                                              :letterSpacing "0.04em"}}])
            [rc-x-axis {:dataKey "idx"
                        :type "number"
                        :domain #js [0 (max 0 (dec n))]
                        :ticks (clj->js tick-idxs)
                        :allowDecimals false
                        :tickFormatter #(or (get tick-labels %) "")
                        :axisLine false
                        :tickLine false
                        :tickMargin 14
                        :interval 0
                        :padding #js {:left 12 :right 12}
                        :tick #js {:fill "var(--fg-3)"
                                   :fontSize 11
                                   :fontFamily "Manrope, sans-serif"
                                   :letterSpacing "0.02em"}}]
            [rc-y-axis {:domain #js [0 y-ceil]
                        :tickFormatter fmt-axis-val
                        :axisLine false
                        :tickLine false
                        :width 56
                        :tickMargin 10
                        :tick #js {:fill "var(--fg-3)"
                                   :fontSize 11
                                   :fontFamily "Manrope, sans-serif"
                                   :letterSpacing "0.02em"}}]
            (when today-x
              [rc-reference-line {:x today-x
                                  :stroke "var(--fg-2)"
                                  :strokeWidth 1
                                  :strokeDasharray "3 4"
                                  :strokeOpacity 0.55
                                  :ifOverflow "extendDomain"}])
            [rc-tooltip {:cursor #js {:stroke "var(--fg-2)"
                                      :strokeWidth 1
                                      :strokeDasharray "3 5"
                                      :strokeOpacity 0.45}
                         :content fluxo-tooltip-content
                         :wrapperStyle #js {:outline "none"}}]
            [rc-area {:type "monotoneX"
                      :dataKey "projetado"
                      :name "projetado"
                      :stroke "var(--blue-regular)"
                      :strokeWidth 2.5
                      :strokeLinecap "round"
                      :strokeLinejoin "round"
                      :fill "url(#fluxo-projetado-fill)"
                      :connectNulls true
                      :isAnimationActive true
                      :animationDuration 700
                      :animationEasing "ease-out"
                      :dot #js {:r 3
                                :strokeWidth 1.5
                                :stroke "var(--bg-1)"
                                :fill "var(--blue-regular)"}
                      :activeDot #js {:r 5
                                      :strokeWidth 2
                                      :stroke "var(--bg-1)"
                                      :fill "var(--blue-regular)"}}]]]])))))

(defn- horizon-card
  "30/60/90d horizon as a self-contained editorial card.
   Top: mono lowercase label.
   Middle: serif amount.
   Bottom: mono apólice count."
  [{:keys [label value detail closing]}]
  [:div.horizon-card
   [:div.horizon-card-head
    [:span.lab label]
    (when closing [:span.horizon-card-close closing])]
   [:div.horizon-card-num (brl-value value "·")]
   [:div.horizon-card-foot
    (when detail [:span.meta detail])]])

(defn- summary-col [{:keys [label value detail]}]
  [:div.col
   [:div.lab label]
   [:div.num (if (= :count (:kind value))
               (:text value)
               (brl-value value "·"))]
   (when detail [:div.meta detail])])

(defn- inspector-metric [{:keys [label value muted?]}]
  [:div.inspector-metric
   [:span label]
   [:strong {:class (when muted? "muted")}
    (if (some? value) (fmt/fmt-brl-int value) "·")]])

(defn- fluxo-inspector-panel
  "Side rail for the selected projected month. It keeps the chart inspectable
   without opening a modal or forcing users into the data table."
  [{:keys [entry total]}]
  (let [{:keys [index point value]} entry
        parts (point-parts point)
        quarter (:q parts)
        year (:y parts)
        realized (->num (:realizado point))
        a-apurar (->num (:a_apurar point))
        projected value]
    [:aside.cash-flow-inspector
     {:aria-label "Competência selecionada no fluxo de caixa"}
     [:div.inspector-eyebrow
      [:span "competência em foco"]
      (when (and index total)
        [:span (str (inc index) "/" total)])]
     [:div.inspector-month
      [:strong (:label point)]
      (when (and quarter year)
        [:span (str "Q" quarter " · " year)])]
     [:div.inspector-total
      [:span "projetado"]
      [:strong (brl-value projected "·")]]
     [:div.inspector-metrics
      [inspector-metric {:label "a apurar" :value a-apurar}]
      [inspector-metric {:label "realizado" :value realized :muted? true}]]
     [:div.inspector-note
      "Use Tab no gráfico para inspecionar outra competência."]]))

(defn- chart-fluxo-caixa-table
  "Tabular alternative to the cash-flow SVG chart. Wrapped in <details> so
   sighted users can disclose it on demand; screen readers read the table
   regardless. Renders only rows that carry at least one numeric value."
  [series]
  (let [rows (filter (fn [p] (or (->num (:realizado p))
                                 (->num (:a_apurar p))
                                 (->num (:projetado p))))
                     series)]
    (when (seq rows)
      [:details.chart-data-table
       [:summary "Ver dados em tabela"]
       [:div.table-wrap
        [:table.table
         [:caption.sr-only
          "Fluxo de caixa mensal por competência: realizado, a apurar e projetado em reais."]
         [:thead
          [:tr
           [:th {:scope "col"} "Mês"]
           [:th.right {:scope "col"} "Realizado"]
           [:th.right {:scope "col"} "A apurar"]
           [:th.right {:scope "col"} "Projetado"]]]
         [:tbody
          (for [p rows]
            ^{:key (:label p)}
            [:tr
             [:th {:scope "row"} (:label p)]
             [:td.right.num (or (fmt/fmt-brl-int (:realizado p)) "·")]
             [:td.right.num (or (fmt/fmt-brl-int (:a_apurar p)) "·")]
             [:td.right.num (or (fmt/fmt-brl-int (:projetado p)) "·")]])]]]])))

(defn- fluxo-caixa-card [{:keys [horizon period-summary filtered? series as-of]}]
  (r/with-let [selected-index* (r/atom nil)]
    (let [projected-count (:apolices period-summary)
          projected (projected-points series)
          fallback-index (default-projected-index series)
          selected-index (or @selected-index* fallback-index)
          selected-entry (or (some #(when (= selected-index (:index %)) %) projected)
                             (first projected))
          active-index (:index selected-entry)
          horizon-months (count projected)]
      [:div.card.fluxo-card
       [:div.card-head
        [:div [:h3 "Fluxo de caixa projetado"]
         [:div.card-sub "comissão a pagar projetada · por competência mensal"]]
        (when as-of [:span.card-asof (str "atualizado " as-of)])]
       (if filtered?
         [:div.horizon-strip.period-summary
          [summary-col {:label "realizado no período"
                        :value (:realizado period-summary)}]
          [summary-col {:label "a apurar no período"
                        :value (:a_apurar period-summary)}]
          [summary-col {:label "projetado no período"
                        :value (:projetado period-summary)}]
          [summary-col {:label "apólices projetadas"
                        :value {:kind :count :text (str (or projected-count 0))}
                        :detail "com parcelas no filtro"}]]
         [:div.horizon-cards
          [horizon-card {:label "próximos 30d"
                         :value (:next_30 horizon)
                         :closing (str "fecha " (horizon-closing-month 30))
                         :detail (when-let [n (:next_30_apolices horizon)]
                                   (str n (if (= n 1) " apólice" " apólices")))}]
          [horizon-card {:label "próximos 60d"
                         :value (:next_60 horizon)
                         :closing (str "fecha " (horizon-closing-month 60))
                         :detail (when-let [n (:next_60_apolices horizon)]
                                   (str n (if (= n 1) " apólice" " apólices")))}]
          [horizon-card {:label "próximos 90d"
                         :value (:next_90 horizon)
                         :closing (str "fecha " (horizon-closing-month 90))
                         :detail (when-let [n (:next_90_apolices horizon)]
                                   (str n (if (= n 1) " apólice" " apólices")))}]])
       [:div.chart-frame
        [:div.chart-legend
         [:span.legend-line "projetado"]
         [:span.legend-month-chip "mês atual"]
         (when (and (not filtered?) (pos? horizon-months))
           [:span.legend-horizon
            "horizonte " [:strong (str horizon-months)] " "
            (if (= 1 horizon-months) "mês" "meses")])]
        [:div.chart-command-surface
         [:div.chart-pane
          [chart-fluxo-caixa series
           {:selected-index active-index
            :on-select #(reset! selected-index* %)}]
          [chart-fluxo-caixa-table series]]
         (when selected-entry
           [fluxo-inspector-panel {:entry selected-entry
                                   :total horizon-months}])]]])))

;; ----- Topbar period control ------------------------------------------

(defn- period-select
  "Two compact selects (year + quarter). Each defaults to \"Todos\"
   (all-time). Dispatches :finance/set-period on change."
  [{:keys [year quarter years future-year-floor]}]
  (let [on-change (fn [kind]
                    (fn [e]
                      (let [v (.. e -target -value)]
                        (rf/dispatch [:finance/set-period kind
                                      (cond
                                        (= v "all") :all
                                        (str/ends-with? v "_plus") v
                                        :else (js/parseInt v 10))]))))
        future-value (when future-year-floor (str future-year-floor "_plus"))
        reset? (or (not= :all year) (not= :all quarter))]
    [:div.period-control {:role "group" :aria-label "Filtro de período"}
     [:span.period-label "período"]
     [:select.period-select {:value (if (= year :all) "all" (str year))
                             :on-change (on-change :year)
                             :aria-label "Ano"}
      [:option {:value "all"} "Todos os anos"]
      (for [y (or years [])]
        ^{:key y} [:option {:value (str y)} (str y)])
      (when future-value
        [:option {:value future-value} (str future-year-floor "+")])]
     [:select.period-select {:value (if (= quarter :all) "all" (str quarter))
                             :on-change (on-change :quarter)
                             :aria-label "Trimestre"}
      [:option {:value "all"} "Todos os trimestres"]
      [:option {:value "1"} "Q1"]
      [:option {:value "2"} "Q2"]
      [:option {:value "3"} "Q3"]
      [:option {:value "4"} "Q4"]]
     (when reset?
       [:button.period-reset
        {:type "button"
         :on-click #(rf/dispatch [:finance/reset-period])}
        "limpar"])]))

(defn finance-dashboard-page []
  (r/with-let [_ (rf/dispatch [:finance/fetch-dashboard])]
    (let [dashboard @(rf/subscribe [:finance/dashboard])
          loading?  @(rf/subscribe [:finance/loading?])
          period    @(rf/subscribe [:finance/period])
          user      @(rf/subscribe [:auth/current-user])
          route     @(rf/subscribe [:current-route-name])

          potencial    (or (:potencial_a_pagar dashboard) (:comissao_potencial dashboard))
          paga         (:comissao_paga dashboard)
          saldo-total  (or (:obrigacao_aberta dashboard) (:saldo_devedor_total dashboard))
          as-of        (format-asof (:as_of dashboard))
          period-tag   (period-suffix period)

          comm-ag        (:comissao_agenciamento dashboard)
          comissao-tot   (:comissao comm-ag)
          agenciam-tot   (:agenciamento comm-ag)
          comm-ag-series (or (:series comm-ag) [])
          comm-ag-period (:period comm-ag)

          fluxo-raw    (:fluxo_caixa dashboard)
          fluxo        (cond
                         (map? fluxo-raw) fluxo-raw
                         (sequential? fluxo-raw) {:series fluxo-raw}
                         :else {})
          fluxo-series (or (:series fluxo) [])
          period-summary (:period_summary fluxo)
          filtered? (or (not= :all (:year period))
                        (not= :all (:quarter period)))
          available-years (or (:available_years dashboard) [2024 2025 2026])
          future-year-floor (:future_year_floor dashboard)]
      [layout/page-shell
       {:current-route route
        :user user
        :crumbs ["plataforma rv" "finance" "dashboard"]
        :title "Visão financeira"
        :subtitle (when loading? "carregando…")
        :header-actions
        [[period-select {:year (:year period)
                         :quarter (:quarter period)
                         :years available-years
                         :future-year-floor future-year-floor}]]}

       ;; Row 1 — three KPIs
       [:div.kpi-grid.-three
        [kpi-potencial {:value potencial
                        :caption (str "a apurar + projetado · " period-tag)}]
        [kpi-paga      {:value paga
                        :caption (str "comissão + agenciamento · " period-tag)}]
        [kpi-saldo     {:value saldo-total
                        :caption (str "NFs recebidas · pendente de pagamento · " period-tag)}]]

       ;; Row 2 — Comissão x Agenciamento
       [comissao-agenciamento-card
        {:comissao comissao-tot
         :agenciamento agenciam-tot
         :series comm-ag-series
         :period comm-ag-period}]

       ;; Row 3 — Fluxo de Caixa Projetado
       [fluxo-caixa-card
        {:horizon (:horizon fluxo)
         :period-summary period-summary
         :filtered? filtered?
         :series fluxo-series
         :as-of as-of}]])))
