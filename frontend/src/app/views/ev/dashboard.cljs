(ns app.views.ev.dashboard
  (:require [clojure.string :as str]
            [reagent.core :as r]
            [re-frame.core :as rf]
            ["recharts" :refer [ResponsiveContainer AreaChart Area XAxis YAxis
                                 CartesianGrid Tooltip ReferenceLine]]
            [app.ds.layout :as layout]
            [app.ds.badge :as badge]
            [app.ds.tokens :as t]
            [app.auth.subs]
            [app.utils.format :as fmt]))

;; -----------------------------------------------------------------------------
;; Helpers
;; -----------------------------------------------------------------------------

(def rc-responsive (r/adapt-react-class ResponsiveContainer))
(def rc-area-chart (r/adapt-react-class AreaChart))
(def rc-area (r/adapt-react-class Area))
(def rc-x-axis (r/adapt-react-class XAxis))
(def rc-y-axis (r/adapt-react-class YAxis))
(def rc-cartesian-grid (r/adapt-react-class CartesianGrid))
(def rc-tooltip (r/adapt-react-class Tooltip))
(def rc-reference-line (r/adapt-react-class ReferenceLine))

(defn- ->num
  "Coerce strings/numbers to a JS number; nil/empty/NaN → nil."
  [v]
  (when (some? v)
    (let [n (cond
              (number? v) v
              (string? v) (let [s (str/trim v)]
                            (when-not (str/blank? s) (js/Number s)))
              :else nil)]
      (when (and (some? n) (js/isFinite n)) n))))

(defn- or-dash [v] (if (or (nil? v) (= v "")) "·" v))

(def ^:private benefit-labels
  {"SAUDE" "Saúde" "ODONTO" "Odonto" "VIDA" "Vida"})

(defn- fmt-benefit [v]
  (or (get benefit-labels v) v "·"))

(defn- fmt-date
  "ISO yyyy-mm-dd → dd/mm/yyyy."
  [iso]
  (if (and iso (string? iso) (>= (count iso) 10))
    (let [[y m d] (str/split (subs iso 0 10) #"-")]
      (str d "/" m "/" y))
    "·"))

(defn- detail-field
  ([label value] (detail-field label value nil))
  ([label value {:keys [wide?]}]
   [:div {:class (str "policy-detail-field" (when wide? " wide"))}
    [:span label]
    [:strong (or value "·")]]))

(defn- money-detail [label value]
  [detail-field label (or (fmt/fmt-brl-int value) "·")])

(defn- pct-bar [pct fill-class]
  (let [n (or (->num pct) 0)]
    [:div.bar
     [:div {:class (str "bar-fill " fill-class)
            :style {:width (str (min n 150) "%")}}]]))

(defn- period-select [{:keys [year quarter years]}]
  (let [year-options (->> (conj (vec (or years [])) year)
                          (filter some?)
                          distinct
                          sort)
        parse-val (fn [v] (when (seq v) (js/parseInt v 10)))]
    [:div.period-filter {:aria-label "Filtrar período"}
     [:select.period-select
      {:value (str year)
       :on-change #(rf/dispatch [:ev/set-period :year (parse-val (.. % -target -value))])}
      [:option {:value ""} "Sem filtro"]
      (for [y year-options]
        ^{:key y} [:option {:value y} y])]
     [:select.period-select
      {:value (str quarter)
       :disabled (nil? year)
       :on-change #(rf/dispatch [:ev/set-period :quarter (parse-val (.. % -target -value))])}
      [:option {:value ""} "Ano inteiro"]
      (for [q [1 2 3 4]]
        ^{:key q} [:option {:value q} (str "Q" q)])]]))

;; -----------------------------------------------------------------------------
;; Projection chart
;; -----------------------------------------------------------------------------

(defn- month-label
  "Backend ships {:month \"YYYY-MM\"}. Render the MM portion as the X label."
  [m]
  (when (and m (string? m) (>= (count m) 7))
    (subs m 5 7)))

(defn projection-chart [pts]
  (let [data (vec (or pts []))
        non-zero? (some #(pos? (or (->num (:projected %)) 0)) data)]
    (if (or (empty? data) (not non-zero?))
      [:div {:style {:padding "32px" :text-align "center" :color "var(--fg-3)"
                     :font-family "var(--font-mono)" :font-size "12px"}}
       "Sem projeção disponível para o período"]
      (let [n (count data)
            x-step (/ 540 (max 1 (dec n)))
            x #(+ 60 (* % x-step))
            max-v (->> data
                       (mapcat (fn [p] [(->num (:projected p)) (->num (:actual p))]))
                       (filter some?)
                       (reduce max 1))
            max-v (if (pos? max-v) max-v 1)
            y #(- 220 (* (/ (or (->num %) 0) max-v) 180))
            proj-pts (->> data
                          (map-indexed (fn [i p]
                                         (when-let [v (->num (:projected p))]
                                           (str (x i) " " (y v)))))
                          (filter some?))
            actual-data (->> data
                             (map-indexed (fn [i p]
                                            (when-let [v (->num (:actual p))]
                                              {:i i :v v})))
                             (filter some?))
            actual-d (->> actual-data
                          (map (fn [p] (str (x (:i p)) " " (y (:v p)))))
                          (str/join " L "))]
        [:svg.chart {:viewBox "0 0 600 240" :preserveAspectRatio "none"}
         [:g {:stroke t/border-default :stroke-width 1}
          [:line {:x1 40 :y1 40  :x2 600 :y2 40}]
          [:line {:x1 40 :y1 100 :x2 600 :y2 100}]
          [:line {:x1 40 :y1 160 :x2 600 :y2 160}]
          [:line {:x1 40 :y1 220 :x2 600 :y2 220}]]
         (when (seq proj-pts)
           [:path {:d (str "M " (str/join " L " proj-pts))
                   :fill "none" :stroke t/blue-500
                   :stroke-width 2 :stroke-dasharray "6 4" :stroke-linecap "round"}])
         (when (seq actual-data)
           [:path {:d (str "M " actual-d) :fill "none" :stroke t/color-primary
                   :stroke-width 2.5 :stroke-linecap "round"}])
         [:g {:fill t/color-primary}
          (for [p actual-data]
            ^{:key (:i p)} [:circle {:cx (x (:i p)) :cy (y (:v p)) :r 3.5}])]
         [:g {:font-family t/font-ui :font-size 11 :fill t/text-tertiary}
          (for [[i p] (map-indexed vector data)]
            ^{:key i}
            [:text {:x (- (x i) 6) :y 238}
             (or (month-label (:month p)) (:label p) "")])]]))))

;; -----------------------------------------------------------------------------
;; Negócios — same ledger surface as the Apólices page, filtered to the EV.
;; -----------------------------------------------------------------------------

(def ^:private pt-months
  ["jan" "fev" "mar" "abr" "mai" "jun"
   "jul" "ago" "set" "out" "nov" "dez"])

(defn- projection-label [p]
  (let [m (:month p)]
    (if (and m (string? m) (>= (count m) 7))
      (let [month-n (js/parseInt (subs m 5 7) 10)
            year (subs m 2 4)]
        (str (get pt-months (dec month-n) (subs m 5 7)) "/" year))
      (or (:label p) ""))))

(defn- projection-summary [pts]
  (let [values (->> pts (map #(->num (:projected %))) (filter some?) vec)
        total (reduce + 0 values)
        peak (when (seq values) (reduce max values))
        first-v (first values)
        last-v (last values)
        delta (when (and (some? first-v) (some? last-v)) (- last-v first-v))]
    {:total total
     :peak peak
     :delta delta
     :months (count values)}))

(defn- compact-money [v]
  (let [n (or (->num v) 0)]
    (cond
      (>= (js/Math.abs n) 1000000) (str "R$ " (.toFixed (/ n 1000000) 1) "M")
      (>= (js/Math.abs n) 1000) (str "R$ " (js/Math.round (/ n 1000)) "k")
      :else (str "R$ " (fmt/int-brl n)))))

(defn- projection-chart-data [pts]
  (->> (or pts [])
       (map-indexed
        (fn [i p]
          (let [v (or (->num (:projected p)) 0)]
            {:idx i
             :month (projection-label p)
             :projected v
             :projectedLabel (or (fmt/fmt-brl-int v) "R$ 0")})))
       vec))

(defn- recharts-tooltip [props]
  (let [p (if (map? props) props (js->clj props :keywordize-keys true))
        active? (:active p)
        payload (first (:payload p))
        row (:payload payload)]
    (when (and active? row)
      (let [row (if (map? row) row (js->clj row :keywordize-keys true))]
        (r/as-element
         [:div.ev-recharts-tooltip
          [:span (:month row)]
          [:strong (:projectedLabel row)]])))))

(def projection-tooltip-content
  (r/reactify-component recharts-tooltip))

(defn- projection-chart-recharts [pts]
  (let [data (projection-chart-data pts)
        peak (when (seq data) (apply max-key :projected data))
        non-zero? (some #(pos? (:projected %)) data)]
    (if (or (empty? data) (not non-zero?))
      [:div.ev-chart-empty "Sem projeção disponível para o período"]
      [:div.ev-recharts-frame
       [rc-responsive {:width "100%" :height 300}
        [rc-area-chart {:data (clj->js data)
                        :margin {:top 12 :right 20 :bottom 8 :left 6}}
         [:defs
          [:linearGradient {:id "evProjectionArea" :x1 "0" :y1 "0" :x2 "0" :y2 "1"}
           [:stop {:offset "0%" :stopColor "var(--blue-light)" :stopOpacity 0.45}]
           [:stop {:offset "72%" :stopColor "var(--blue-light)" :stopOpacity 0.08}]
           [:stop {:offset "100%" :stopColor "var(--blue-light)" :stopOpacity 0}]]]
         [rc-cartesian-grid {:stroke "var(--border-subtle)"
                             :strokeDasharray "2 5"
                             :vertical false}]
         [rc-x-axis {:dataKey "month"
                     :axisLine false
                     :tickLine false
                     :tickMargin 14
                     :interval 0
                     :minTickGap 10
                     :tick {:fill "var(--fg-3)"
                            :fontSize 11
                            :fontFamily "var(--font-mono)"}}]
         [rc-y-axis {:axisLine false
                     :tickLine false
                     :width 64
                     :tickMargin 10
                     :tickFormatter compact-money
                     :tick {:fill "var(--fg-3)"
                            :fontSize 11
                            :fontFamily "var(--font-mono)"}}]
         [rc-tooltip {:cursor {:stroke "var(--fg-3)"
                               :strokeWidth 1
                               :strokeDasharray "3 4"}
                      :content projection-tooltip-content}]
         (when peak
           [rc-reference-line {:x (:month peak)
                               :stroke "var(--fg-3)"
                               :strokeDasharray "3 4"
                               :label {:value (str "pico " (:projectedLabel peak))
                                       :position "top"
                                       :fill "var(--fg-1)"
                                       :fontSize 11
                                       :fontFamily "var(--font-mono)"}}])
         [rc-area {:type "monotoneX"
                   :dataKey "projected"
                   :name "projetado"
                   :stroke "var(--blue-regular)"
                   :strokeWidth 2.5
                   :fill "url(#evProjectionArea)"
                   :dot {:r 3
                         :strokeWidth 1.5
                         :stroke "var(--bg-1)"
                         :fill "var(--blue-regular)"}
                   :activeDot {:r 5
                               :strokeWidth 2
                               :stroke "var(--bg-1)"
                               :fill "var(--blue-regular)"}}]]]])))

(defn projection-chart-rich [pts]
  (let [data (vec (or pts []))
        non-zero? (some #(pos? (or (->num (:projected %)) 0)) data)]
    (if (or (empty? data) (not non-zero?))
      [:div.ev-chart-empty "Sem projeção disponível para o período"]
      (let [n (count data)
            lft 74 rgt 730 tp 24 btm 246
            plot-w (- rgt lft)
            plot-h (- btm tp)
            x-step (/ plot-w (max 1 (dec n)))
            x #(+ lft (* % x-step))
            max-v (->> data
                       (map #(->num (:projected %)))
                       (filter some?)
                       (reduce max 1))
            y-ceil (* (js/Math.ceil (/ max-v 10000)) 10000)
            y-ceil (if (pos? y-ceil) y-ceil max-v)
            y #(- btm (* (/ (or (->num %) 0) y-ceil) plot-h))
            proj-data (->> data
                           (map-indexed (fn [i p]
                                          (when-let [v (->num (:projected p))]
                                            {:i i :v v :x (x i) :y (y v) :p p})))
                           (filter some?)
                           vec)
            proj-pts (map (fn [{:keys [x y]}] (str x " " y)) proj-data)
            area-d (when (seq proj-pts)
                     (str "M " (str/join " L " proj-pts)
                          " L " (:x (last proj-data)) " " btm
                          " L " (:x (first proj-data)) " " btm " Z"))
            ticks [0 (/ y-ceil 4) (/ y-ceil 2) (* y-ceil 0.75) y-ceil]
            peak-entry (when (seq proj-data) (apply max-key :v proj-data))]
        [:svg.chart.ev-projection-svg
         {:viewBox "0 0 760 300"
          :preserveAspectRatio "none"
          :role "img"
          :aria-label "Projeção mensal de comissão estimada"}
         [:defs
          [:linearGradient {:id "ev-projection-fill" :x1 "0" :y1 "0" :x2 "0" :y2 "1"}
           [:stop {:offset "0%" :stop-color "var(--blue-light)" :stop-opacity 0.28}]
           [:stop {:offset "70%" :stop-color "var(--blue-light)" :stop-opacity 0.06}]
           [:stop {:offset "100%" :stop-color "var(--blue-light)" :stop-opacity 0}]]]
         [:rect {:x lft :y tp :width plot-w :height plot-h :rx 8
                 :fill "var(--bg-1)"
                 :stroke "var(--border-subtle)"
                 :stroke-width 1
                 :vector-effect "non-scaling-stroke"}]
         [:g.ev-chart-grid
          (for [tv ticks]
            ^{:key (str "tick-" tv)}
            [:g
             [:line {:x1 lft :x2 rgt :y1 (y tv) :y2 (y tv)}]
             [:text {:x (- lft 12) :y (+ (y tv) 4) :text-anchor "end"}
              (cond
                (zero? tv) "0"
                (>= tv 1000000) (str (.toFixed (/ tv 1000000) 1) "M")
                :else (str (js/Math.round (/ tv 1000)) "k"))]])]
         (when area-d
           [:path {:d area-d :fill "url(#ev-projection-fill)"}])
         (when (seq proj-pts)
           [:path.ev-projection-line
            {:d (str "M " (str/join " L " proj-pts))
             :fill "none"
             :stroke "var(--blue-regular)"
             :stroke-width 2.5
             :stroke-linecap "round"
             :stroke-linejoin "round"
             :vector-effect "non-scaling-stroke"}])
         [:g.ev-chart-dots
          (for [{:keys [i x y v p]} proj-data]
            ^{:key i}
            [:g
             [:circle {:cx x :cy y :r 3.5}]
             [:title (str (projection-label p) " · " (or (fmt/fmt-brl-int v) "R$ 0"))]])]
         (when peak-entry
           (let [label-y (max (+ tp 8) (- (:y peak-entry) 34))]
             [:g.ev-chart-peak
              [:line {:x1 (:x peak-entry) :x2 (:x peak-entry)
                      :y1 tp :y2 btm}]
              [:rect {:x (- (:x peak-entry) 42) :y label-y
                      :width 84 :height 24 :rx 6}]
              [:text {:x (:x peak-entry) :y (+ label-y 16)
                      :text-anchor "middle"}
               (str "pico " (or (fmt/fmt-brl-int (:v peak-entry)) "R$ 0"))]]))
         [:g.ev-chart-x
          (for [[i p] (map-indexed vector data)]
            ^{:key i}
            [:text {:x (x i) :y 280 :text-anchor "middle"}
             (projection-label p)])]]))))

(def ^:private deals-row-h 52)

(def ^:private deals-cols
  ;; Mirrors the Apólices ledger but drops the EV column (logged-in user owns
  ;; every row, so repeating the name 20× would be pure noise).
  (str "[ticket] minmax(112px,0.86fr) "
       "[apolice] minmax(108px,0.82fr) "
       "[cliente] minmax(220px,1.7fr) "
       "[operadora] minmax(132px,0.95fr) "
       "[beneficio] minmax(96px,0.72fr) "
       "[data] minmax(112px,0.78fr) "
       "[estado] minmax(154px,0.98fr)"))

(defn- deals-ledger [policies loading? focused-id]
  (let [items (vec (or policies []))
        n (count items)
        total-h (* n deals-row-h)
        detail-policy (some #(when (= (:id %) @focused-id) %) items)]
    [:div.card.ev-deals-card {:style {:padding 0}}
     [:div.ev-deals-head
      [:h3 "Negócios"]
      [:div.card-sub (str n " apólice" (when (not= 1 n) "s") " no período")]]
     [:div.policies-overdrive {:style {:gap 0}}
      [:div.policies-workspace {:data-detail-open (str (boolean detail-policy))}
       [:div.ledger {:style {"--cols" deals-cols
                            :max-height "560px"}}
       [:div.ledger-head {:role "row"}
        [:div.col "Ticket ID"]
        [:div.col "Apólice"]
        [:div.col "Cliente"]
        [:div.col "Operadora"]
        [:div.col "Benefício"]
        [:div.col "Data Gongo"]
        [:div.col "Estado"]]
       [:div.ledger-body
        (cond
          (and loading? (zero? n))
          [:div.ledger-state [:span.pulse] "carregando…"]

          (zero? n)
          [:div.ledger-state "nenhum negócio encontrado"]

          :else
          [:div.ledger-spacer {:style {:height (str total-h "px")}}
            [:div.ledger-rows {:role "rowgroup"}
             (for [[i p] (map-indexed vector items)
                   :let [id (:id p)
                         focused? (= id @focused-id)]]
               ^{:key (or id (:hubspot_ticket_id p) i)}
               [:div.ledger-row
                {:role "row"
                 :tab-index 0
                 :aria-selected (str focused?)
                 :data-focused (str focused?)
                 :style {:top (str (* i deals-row-h) "px")}
                 :on-click #(reset! focused-id id)
                 :on-key-down (fn [e]
                                (when (#{"Enter" " "} (.-key e))
                                  (.preventDefault e)
                                  (reset! focused-id id)))}
               [:div.col.num.muted (or-dash (:hubspot_ticket_id p))]
               [:div.col.name.num (or-dash (:numero_apolice p))]
               [:div.col (or (:client_name p) "·")]
               [:div.col.muted (or-dash (:partner_operator p))]
               [:div.col.muted (fmt-benefit (:benefit_type p))]
               [:div.col.num.muted (fmt-date (:closed_date p))]
               [:div.col.estado
                [badge/status-badge {:status (:commission_status p)}]]])]])]]
       (when detail-policy
         [:aside.policy-detail.ev-policy-detail {:aria-label "Detalhes do negócio"}
          [:div.policy-detail-head
           [:div.policy-detail-title
            [:span "apólice"]
            [:h3 (or-dash (:numero_apolice detail-policy))]
            [:p (str "Ticket " (or-dash (:hubspot_ticket_id detail-policy)))]]
           [:button.policy-detail-close
            {:type "button"
             :on-click #(reset! focused-id nil)}
            "Fechar"]]
          [:div.policy-detail-status
           [badge/status-badge {:status (:commission_status detail-policy)}]]

          [:div.policy-detail-section
           [:div.policy-detail-section-title "Financeiro"]
           [:div.policy-detail-grid
            [money-detail "MRR" (:mrr_for_commission detail-policy)]
            [money-detail "Comissão potencial" (:commission_potential detail-policy)]
            [money-detail "Total pago" (:commission_paid_total detail-policy)]
            [money-detail "Pago comissão" (:total_paid_comissao detail-policy)]
            [money-detail "Pago agenciamento" (:total_paid_agenciamento detail-policy)]
            [detail-field "Meses" (str (or (:installments_paid detail-policy) 0) "/12")]]]

          [:div.policy-detail-section
           [:div.policy-detail-section-title "Origem"]
           [:div.policy-detail-grid
            [detail-field "Cliente" (or (:client_name detail-policy) "·") {:wide? true}]
            [detail-field "Operadora" (or-dash (:partner_operator detail-policy))]
            [detail-field "Benefício" (fmt-benefit (:benefit_type detail-policy))]
            [detail-field "Data gongo" (fmt-date (:closed_date detail-policy))]
            [detail-field "Status HubSpot" (or-dash (:hubspot_stage detail-policy))]]]])]]]))

;; -----------------------------------------------------------------------------
;; Page
;; -----------------------------------------------------------------------------

(defn dashboard-page []
  (let [focused-id (r/atom nil)]
    (rf/dispatch [:ev/fetch-dashboard])
    (rf/dispatch [:ev/fetch-policies nil])
    (rf/dispatch [:ev/fetch-projection])
    (fn []
    (let [summary    @(rf/subscribe [:ev/summary])
          projection @(rf/subscribe [:ev/projection])
          policies   @(rf/subscribe [:ev/policies])
          selected-period @(rf/subscribe [:ev/period])
          pol-loading? @(rf/subscribe [:ev/policies-loading?])
          user       @(rf/subscribe [:auth/current-user])
          route      @(rf/subscribe [:current-route-name])
          balance    (->num (:balance_estimated summary))
          pct        (->num (:achievement_pct summary))
          target     (->num (:mrr_target summary))
          mrr-sold   (->num (:mrr_sold summary))
          quarter    (or (:current_quarter summary) (:quarter selected-period))
          year       (or (:current_year summary) (:year selected-period))
          period     (cond
                       (and quarter year) (str "Q" quarter "/" year)
                       year               (str year)
                       :else              "total")
          available-years (:available_years summary)
          proj-s     (projection-summary projection)]
      [layout/page-shell
       {:current-route route :user user
        :crumbs ["plataforma rv" "ev" "dashboard"]
        :title (str "Bem-vindo, " (or (some-> (:name user) (str/split #" ") first) "EV"))
        :subtitle (cond
                    (and quarter year) (str "Q" quarter "/" year " em validação")
                    year               (str "ano " year)
                    :else              "carteira total")
        :header-actions [[period-select {:year year
                                          :quarter quarter
                                          :years available-years}]]}

       [:div.ev-dashboard
        [:section.ev-dashboard-overview
         [:div.ev-metric-column
          [:div.card.ev-balance-card
           [:div.ev-balance-head
            [:div.kpi-label
             [layout/icon "money" {:width 14 :height 14}]
             "saldo a receber"]
            (when period [:span.card-asof period])]
           [:div.ev-balance-value
            [:span.currency "R$"]
            (or (fmt/int-brl balance) "·")]
           [:div.ev-balance-foot
            [:span.badge.badge-draft
             (str (count (or policies [])) " negócios")]
            [:span (if period (str "estimativa " period) "estimativa em aberto")]]]

          [:div.ev-compact-metrics
           [:div.ev-compact-metric
            [:div.kpi-label
             [layout/icon "target" {:width 14 :height 14}]
             "atingimento"]
            [:div.ev-compact-value
             (if (some? pct) [:<> (.toFixed pct 0) [:span.frac "%"]] "·")]
            (when (some? pct)
              [pct-bar pct (cond (>= pct 100) "success" (>= pct 70) "warn" :else "danger")])]
           [:div.ev-compact-metric
            [:div.kpi-label
             [layout/icon "target" {:width 14 :height 14}]
             "meta"]
            [:div.ev-compact-value
             [:span.currency "R$"]
             (or (fmt/int-brl target) "·")]
            [:div.ev-compact-caption
             (if (some? mrr-sold)
               (str "MRR vendido: R$ " (fmt/int-brl mrr-sold))
               "MRR vendido pendente")]]]]

         [:div.card.ev-projection-card
          [:div.card-head
           [:div
            [:h3 "Projeção mensal"]
            [:div.card-sub (str (:months proj-s) " competências projetadas")]]
           [:div.legend
            [:span.legend-line {:style {:color "var(--blue-regular)"}} "projetado"]]]
          [:div.ev-chart-stats
           [:div
            [:span "total projetado"]
            [:strong (or (fmt/fmt-brl-int (:total proj-s)) "R$ 0")]]
           [:div
            [:span "pico mensal"]
            [:strong (or (fmt/fmt-brl-int (:peak proj-s)) "R$ 0")]]
           [:div
            [:span "variação"]
            [:strong (or (fmt/fmt-brl-int (:delta proj-s)) "R$ 0")]]]
          [projection-chart-recharts projection]]]

        ;; Deals — mirrors the Apólices ledger, filtered to this EV by the API.
        [deals-ledger policies pol-loading? focused-id]]]))))
