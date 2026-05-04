(ns app.views.ev.dashboard
  (:require [re-frame.core :as rf]
            [app.ds.layout :as layout]
            [app.ds.typography :as typo]
            [app.auth.subs]
            [app.utils.format :as fmt]))

(defn- pct-bar [pct fill-class]
  [:div.bar
   [:div {:class (str "bar-fill " fill-class)
          :style {:width (str (min (or pct 0) 150) "%")}}]])

(defn- status->badge [status]
  (case status
    "PROJECTED"  [:span.badge.badge-paid "Ativa"]
    "IN_PAYMENT" [:span.badge.badge-validating "Em validação"]
    "SETTLED"    [:span.badge.badge-paid "Pago"]
    "CANCELLED"  [:span.badge.badge-contested "Cancelado"]
    [:span.badge.badge-paid "Ativa"]))

(defn- projection-chart [pts]
  (if (empty? pts)
    [:div {:style {:padding "32px" :text-align "center" :color "var(--fg-3)"
                   :font-family "var(--font-mono)" :font-size "12px"}}
     "Sem projeção disponível para o período"]
    (let [data (vec pts)
          n (count data)
          x-step (/ 540 (max 1 (dec n)))
          x #(+ 60 (* % x-step))
          max-v (or (->> data (mapcat (fn [p] [(:projected p) (:actual p)]))
                         (filter some?) (reduce max 1)) 1)
          y #(- 220 (* (/ (or % 0) max-v) 180))
          proj-pts (->> data
                        (map-indexed (fn [i p] (when-let [v (:projected p)]
                                                 (str (x i) " " (y v)))))
                        (filter some?))
          actual-pts (filter :actual (map-indexed #(assoc %2 :i %1) data))
          actual-d (->> actual-pts (map (fn [p] (str (x (:i p)) " " (y (:actual p)))))
                         (clojure.string/join " L "))]
      [:svg.chart {:viewBox "0 0 600 240" :preserveAspectRatio "none"}
       [:g {:stroke "#E2E1DF" :stroke-width 1}
        [:line {:x1 40 :y1 40  :x2 600 :y2 40}]
        [:line {:x1 40 :y1 100 :x2 600 :y2 100}]
        [:line {:x1 40 :y1 160 :x2 600 :y2 160}]
        [:line {:x1 40 :y1 220 :x2 600 :y2 220}]]
       (when (seq proj-pts)
         [:path {:d (str "M " (clojure.string/join " L " proj-pts))
                 :fill "none" :stroke "#3370D1"
                 :stroke-width 2 :stroke-dasharray "6 4" :stroke-linecap "round"}])
       (when (seq actual-pts)
         [:path {:d (str "M " actual-d) :fill "none" :stroke "#000"
                 :stroke-width 2.5 :stroke-linecap "round"}])
       [:g {:fill "#000"}
        (for [p actual-pts]
          ^{:key (:i p)} [:circle {:cx (x (:i p)) :cy (y (:actual p)) :r 3.5}])]
       [:g {:font-family "Manrope" :font-size 11 :fill "#6B6663"}
        (for [[i p] (map-indexed vector data)]
          ^{:key i} [:text {:x (- (x i) 6) :y 238} (:label p)])]])))

(defn- deals-table-section [policies loading?]
  (let [items (or (seq policies) [])]
    [:div.card {:style {:padding 0}}
     [:div {:style {:padding "24px 24px 16px"}}
      [:h3 "Negócios"]
      [:div.card-sub (str (count items) " apólice" (when (not= 1 (count items)) "s") " no período")]]
     [:table.table
      [:thead
       [:tr
        [:th "Apólice"]
        [:th "Cliente"]
        [:th "Benefício"]
        [:th.center "Vidas"]
        [:th.right "MRR"]
        [:th.right "Comissão"]
        [:th "Status"]]]
      [:tbody
       (cond
         loading?
         (for [i (range 4)]
           ^{:key i}
           [:tr
            [:td {:col-span 7 :class "loading-cell"}
             [:div.skel-row
              (for [w [80 140 100 50 90 90 80]]
                ^{:key w} [:div.skel {:style {:width (str w "px") :height "14px"}}])]]])

         (empty? items)
         [:tr
          [:td {:col-span 7 :style {:padding "48px 16px" :text-align "center" :color "var(--fg-3)"}}
           "Nenhum negócio encontrado"]]

         :else
         (for [row items]
           ^{:key (or (:id row) (:hubspot_ticket_id row) (hash row))}
           [:tr
            [:td.name.num (or (:policy_id row) (:hubspot_ticket_id row) "·")]
            [:td (:client_name row)]
            [:td.muted (or (:benefit_type row) "·")]
            [:td.center.num (str (or (:lives row) (:installments_paid row) "·"))]
            [:td.right.strong-num (str "R$ " (or (fmt/int-brl (:mrr_projected row)) "·"))]
            [:td.right.strong-num (str "R$ " (or (fmt/int-brl (:mrr_for_commission row)) "·"))]
            [:td [status->badge (:commission_status row)]]]))]]]))

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
          balance    (:balance_estimated summary)
          pct        (:achievement_pct summary)
          target     (:mrr_target summary)
          mrr-sold   (:mrr_sold summary)
          quarter    (:current_quarter summary)
          year       (:current_year summary)
          period     (when (and quarter year) (str "Q" quarter "/" year))]
      [layout/page-shell
       {:current-route route :user user
        :crumbs ["plataforma rv" "ev" "dashboard"]
        :title (str "Bem-vindo, " (or (some-> (:name user) (clojure.string/split #" ") first) "EV"))
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
          (when mrr-sold
            [:<> "MRR vendido: "
             [:strong {:style {:color "var(--fg-1)"}} (str "R$ " (fmt/int-brl mrr-sold))]])]]]

       ;; ── Projeção ───────────────────────────────────
       [typo/section-heading
        {:lab "projeção"
         :title "Mês a mês"}]

       [:div.card
        [:div.card-head
         [:div [:h3 "Projeção mensal"] [:div.card-sub "Projetado vs. realizado"]]
         [:div.legend
          [:span.legend-line {:style {:color "var(--blue-regular)"}} "projetado"]
          [:span.legend-dot  {:style {:color "var(--black)"}} "realizado"]]]
        [projection-chart projection]]

       ;; ── Negócios ───────────────────────────────────
       [typo/section-heading
        {:lab "negócios"
         :title "Apólices do período"}]

       [deals-table-section policies pol-loading?]])))
