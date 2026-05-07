(ns app.views.ev.dashboard
  (:require [clojure.string :as str]
            [re-frame.core :as rf]
            [app.ds.layout :as layout]
            [app.ds.badge :as badge]
            [app.ds.tokens :as t]
            [app.auth.subs]
            [app.utils.format :as fmt]))

;; -----------------------------------------------------------------------------
;; Helpers
;; -----------------------------------------------------------------------------

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

(defn- pct-bar [pct fill-class]
  (let [n (or (->num pct) 0)]
    [:div.bar
     [:div {:class (str "bar-fill " fill-class)
            :style {:width (str (min n 150) "%")}}]]))

;; -----------------------------------------------------------------------------
;; Projection chart
;; -----------------------------------------------------------------------------

(defn- month-label
  "Backend ships {:month \"YYYY-MM\"}. Render the MM portion as the X label."
  [m]
  (when (and m (string? m) (>= (count m) 7))
    (subs m 5 7)))

(defn- projection-chart [pts]
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

(defn- deals-ledger [policies loading?]
  (let [items (vec (or policies []))
        n (count items)
        total-h (* n deals-row-h)]
    [:div.card {:style {:padding 0}}
     [:div {:style {:padding "24px 24px 16px"}}
      [:h3 "Negócios"]
      [:div.card-sub (str n " apólice" (when (not= 1 n) "s") " no período")]]
     [:div.policies-overdrive {:style {:gap 0}}
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
            (for [[i p] (map-indexed vector items)]
              ^{:key (or (:id p) (:hubspot_ticket_id p) i)}
              [:div.ledger-row
               {:role "row"
                :style {:top (str (* i deals-row-h) "px")}}
               [:div.col.num.muted (or-dash (:hubspot_ticket_id p))]
               [:div.col.name.num (or-dash (:numero_apolice p))]
               [:div.col (or (:client_name p) "·")]
               [:div.col.muted (or-dash (:partner_operator p))]
               [:div.col.muted (fmt-benefit (:benefit_type p))]
               [:div.col.num.muted (fmt-date (:closed_date p))]
               [:div.col.estado
                [badge/status-badge {:status (:commission_status p)}]]])]])]]]]))

;; -----------------------------------------------------------------------------
;; Page
;; -----------------------------------------------------------------------------

(defn dashboard-page []
  (rf/dispatch [:ev/fetch-dashboard])
  (rf/dispatch [:ev/fetch-policies nil])
  (rf/dispatch [:ev/fetch-projection])
  (fn []
    (let [summary    @(rf/subscribe [:ev/summary])
          projection @(rf/subscribe [:ev/projection])
          policies   @(rf/subscribe [:ev/policies])
          pol-loading? @(rf/subscribe [:ev/policies-loading?])
          user       @(rf/subscribe [:auth/current-user])
          route      @(rf/subscribe [:current-route-name])
          balance    (->num (:balance_estimated summary))
          pct        (->num (:achievement_pct summary))
          target     (->num (:mrr_target summary))
          mrr-sold   (->num (:mrr_sold summary))
          quarter    (:current_quarter summary)
          year       (:current_year summary)
          period     (when (and quarter year) (str "Q" quarter "/" year))]
      [layout/page-shell
       {:current-route route :user user
        :crumbs ["plataforma rv" "ev" "dashboard"]
        :title (str "Bem-vindo, " (or (some-> (:name user) (str/split #" ") first) "EV"))
        :subtitle (when period (str period " em validação"))
        :header-actions nil}

       ;; KPIs (3-up)
       [:div.kpi-grid.-three
        ;; Black highlighted card — saldo a receber
        [:div.kpi {:style {:background "var(--night)" :color "#fff"
                           :border-color "var(--night)" :position "relative"
                           :overflow "hidden"}}
         [:div.kpi-label {:style {:color "rgba(255,255,255,.65)"}}
          [layout/icon "money" {:width 14 :height 14}]
          "saldo a receber"]
         [:div.kpi-value {:style {:color "#fff"}}
          [:span.currency {:style {:color "rgba(255,255,255,.65)"}} "R$"]
          (or (fmt/int-brl balance) "·")]
         [:div.kpi-foot {:style {:color "rgba(255,255,255,.65)"}}
          [:span.badge {:style {:background "rgba(255,255,255,.12)" :color "#fff"}}
           (str (count (or policies [])) " negócios")]
          (when period (str " · estimativa " period))]
         [:svg.kpi-grafismo {:style {:color "var(--cyan)" :opacity 0.18}}
          [:use {:href "#i-grafismo"}]]]

        [:div.kpi
         [:div.kpi-label [layout/icon "target" {:width 14 :height 14}] "atingimento do período"]
         [:div.kpi-value
          (if (some? pct) [:<> (.toFixed pct 0) [:span.frac "%"]] "·")]
         [:div.kpi-foot
          (when (some? pct)
            [pct-bar pct (cond (>= pct 100) "success" (>= pct 70) "warn" :else "danger")])]]

        [:div.kpi
         [:div.kpi-label [layout/icon "target" {:width 14 :height 14}] "meta do período"]
         [:div.kpi-value [:span.currency "R$"] (or (fmt/int-brl target) "·")]
         [:div.kpi-foot
          (when (some? mrr-sold)
            [:<> "MRR vendido: "
             [:strong {:style {:color "var(--fg-1)"}} (str "R$ " (fmt/int-brl mrr-sold))]])]]]

       ;; Projection chart
       [:div.card
        [:div.card-head
         [:div [:h3 "Projeção mensal"] [:div.card-sub "Projetado vs. realizado"]]
         [:div.legend
          [:span.legend-line {:style {:color "var(--blue-regular)"}} "projetado"]
          [:span.legend-dot  {:style {:color "var(--black)"}} "realizado"]]]
        [projection-chart projection]]

       ;; Deals — mirrors the Apólices ledger, filtered to this EV by the API.
       [deals-ledger policies pol-loading?]])))
