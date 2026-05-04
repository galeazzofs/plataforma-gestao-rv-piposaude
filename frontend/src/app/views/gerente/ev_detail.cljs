(ns app.views.gerente.ev-detail
  (:require [re-frame.core :as rf]
            [app.ds.layout :as layout]
            [app.auth.subs]))

;; Detalhe do EV (visão do gerente) — mirrors the design's "Apuração detalhe"
;; layout: KPIs row + memória de cálculo table.

(defn- fmt-int [v]
  (when v (.toLocaleString (js/Math.round (if (string? v) (js/parseFloat v) v)) "pt-BR")))

(defn- pct-bar [pct fill-class]
  [:div.bar
   [:div {:class (str "bar-fill " fill-class)
          :style {:width (str (min (or pct 0) 150) "%")}}]])

(defn- pct-class [pct]
  (cond (>= (or pct 0) 100) "success" (>= (or pct 0) 70) "warn" :else "danger"))

(defn ev-detail-page []
  (let [route-params (rf/subscribe [:current-route])]
    (fn []
      (let [ev-id    (get-in @route-params [:path-params :ev-id])
            _        (when ev-id (rf/dispatch [:gerente/fetch-ev-detail ev-id]))
            ev-data  @(rf/subscribe [:gerente/ev-detail])
            loading? @(rf/subscribe [:gerente/ev-detail-loading?])
            user     @(rf/subscribe [:auth/current-user])
            route    @(rf/subscribe [:current-route-name])
            policies (or (:policies ev-data) [])
            ev-name  (or (:name ev-data) "EV")
            quarter  (or (:quarter ev-data) "·")
            year     (or (:year ev-data) "·")
            pct      (or (:achievement_pct ev-data) 0)]
        [layout/page-shell
         {:current-route route :user user
          :crumbs ["plataforma rv" "gerente" "EV" (str ev-name)]
          :title (str ev-name " · Q" quarter "/" year)
          :subtitle "Apuração individual · em revisão"
          :header-actions
          [[:button.btn.btn-secondary
            {:on-click #(rf/dispatch [:navigate :gerente/dashboard])}
            "Devolver para cálculo"]
           [:button.btn.btn-primary
            {:on-click #(rf/dispatch [:gerente/approve-ev ev-id])}
            [layout/icon "check" {:width 14 :height 14}] "Aprovar valores"]]}

         (if loading?
           [:div {:style {:padding "32px" :text-align "center" :color "var(--fg-3)"}} "Carregando…"]
           [:<>
            ;; KPIs
            [:div.kpi-grid
             [:div.kpi
              [:div.kpi-label "comissão total"]
              [:div.kpi-value [:span.currency "R$"] (or (fmt-int (:commission_total ev-data)) "·")]]
             [:div.kpi
              [:div.kpi-label "atingimento"]
              [:div.kpi-value (str (.toFixed pct 0)) [:span.frac "%"]]
              [:div.kpi-foot
               [pct-bar pct (pct-class pct)]]]
             [:div.kpi
              [:div.kpi-label "multiplicador"]
              [:div.kpi-value (or (some-> (:multiplier ev-data) (str)) "1,00")
               [:span.frac "x"]]]
             [:div.kpi
              [:div.kpi-label "negócios apurados"]
              [:div.kpi-value (str (count policies))]]]

            ;; Memória de cálculo
            [:div.card {:style {:padding 0}}
             [:div {:style {:padding "18px 20px 0"}}
              [:h3 "Memória de cálculo"]
              [:div.card-sub "Composição da comissão por apólice"]]
             [:table.table
              [:thead
               [:tr
                [:th "Apólice"]
                [:th "Cliente"]
                [:th.right "MRR"]
                [:th.right "% comissão"]
                [:th.right "Multipl."]
                [:th.right "Bruto"]
                [:th "Status"]]]
              [:tbody
               (if (empty? policies)
                 [:tr [:td {:col-span 7 :style {:padding "32px" :text-align "center" :color "var(--fg-3)"}}
                       "Nenhum negócio neste período"]]
                 (for [p policies]
                   ^{:key (or (:id p) (:numero_apolice p) (hash p))}
                   [:tr
                    [:td.name.num (or (:numero_apolice p) "·")]
                    [:td (:client_name p)]
                    [:td.right.strong-num (str "R$ " (or (fmt-int (:mrr_for_commission p)) "·"))]
                    [:td.right.num (str (or (:commission_pct p) "·") "%")]
                    [:td.right.num (str (or (:multiplier p) "1,00") "x")]
                    [:td.right.strong-num (str "R$ " (or (fmt-int (:commission_amount p)) "·"))]
                    [:td (case (:commission_status p)
                           "SETTLED"   [:span.badge.badge-paid "OK"]
                           "PROJECTED" [:span.badge.badge-paid "OK"]
                           "IN_PAYMENT"[:span.badge.badge-review "Verificar"]
                           [:span.badge.badge-review "Verificar"])]]))]]]])]))))
