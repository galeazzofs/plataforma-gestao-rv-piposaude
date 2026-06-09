(ns app.views.lider-vendas.ev-detail
  (:require [reagent.core :as r]
            [re-frame.core :as rf]
            [app.ds.layout :as layout]
            [app.auth.subs]))

(defn- num [v]
  (cond
    (nil? v) 0
    (number? v) v
    (string? v) (or (js/parseFloat v) 0)
    :else 0))

(defn- fmt-int [v]
  (when v (.toLocaleString (js/Math.round (num v)) "pt-BR")))

(defn- pct-bar [pct fill-class]
  [:div.bar
   [:div {:class (str "bar-fill " fill-class)
          :style {:width (str (min (num pct) 150) "%")}}]])

(defn- pct-class [pct]
  (let [value (num pct)]
    (cond (>= value 100) "success" (>= value 70) "warn" :else "danger")))

(defn ev-detail-page []
  ;; Track the last-fetched ev-id so we dispatch the fetch only on mount or when
  ;; navigating to a different EV — NOT on every re-render. Dispatching inside
  ;; the render unconditionally caused an infinite fetch→re-render→fetch loop.
  (let [fetched (r/atom nil)]
    (fn []
      (let [route-params @(rf/subscribe [:current-route])
            ev-id    (get-in route-params [:path-params :ev-id])
            _        (when (and ev-id (not= ev-id @fetched))
                       (reset! fetched ev-id)
                       (rf/dispatch [:lider-vendas/fetch-ev-detail ev-id]))
            ev-data  @(rf/subscribe [:lider-vendas/ev-detail])
            loading? @(rf/subscribe [:lider-vendas/ev-detail-loading?])
            user     @(rf/subscribe [:auth/current-user])
            route    @(rf/subscribe [:current-route-name])
            policies (or (:policies ev-data) [])
            ev-name  (or (:name ev-data) (get-in ev-data [:ev :name]) "EV")
            quarter  (or (:quarter ev-data) "-")
            year     (or (:year ev-data) "-")
            pct      (num (:achievement_pct ev-data))]
        [layout/page-shell
         {:current-route route :user user
          :crumbs ["plataforma rv" "lider de vendas" "EV" (str ev-name)]
          :title (str ev-name " Q" quarter "/" year)
          :subtitle "Memoria de calculo da ultima apuracao"
          :header-actions
          [[:button.btn.btn-secondary
            {:on-click #(rf/dispatch [:navigate :lider-vendas/dashboard])}
            "Voltar ao painel"]]}

         (if loading?
           [:div {:style {:padding "32px" :text-align "center" :color "var(--fg-3)"}} "Carregando..."]
           [:<>
            [:div.kpi-grid
             [:div.kpi
              [:div.kpi-label "comissao total"]
              [:div.kpi-value [:span.currency "R$"] (or (fmt-int (:commission_total ev-data)) "0")]]
             [:div.kpi
              [:div.kpi-label "atingimento"]
              [:div.kpi-value (str (.toFixed pct 0)) [:span.frac "%"]]
              [:div.kpi-foot [pct-bar pct (pct-class pct)]]]
             [:div.kpi
              [:div.kpi-label "multiplicador"]
              [:div.kpi-value "1,00" [:span.frac "x"]]]
             [:div.kpi
              [:div.kpi-label "negocios apurados"]
              [:div.kpi-value (str (count policies))]]]

            [:div.card {:style {:padding 0}}
             [:div {:style {:padding "18px 20px 0"}}
              [:h3 "Memoria de calculo"]
              [:div.card-sub "Composicao da comissao por apolice"]]
             [:table.table
              [:thead
               [:tr
                [:th "Apolice"]
                [:th "Cliente"]
                [:th.right "MRR"]
                [:th.right "Atingim."]
                [:th.right "% comissao"]
                [:th.right "Multipl."]
                [:th.right "Bruto"]
                [:th "Status"]]]
              [:tbody
               (if (empty? policies)
                 [:tr [:td {:col-span 8 :style {:padding "32px" :text-align "center" :color "var(--fg-3)"}}
                       "Nenhum negocio neste periodo"]]
                 (for [policy policies]
                   ^{:key (or (:id policy) (:numero_apolice policy) (hash policy))}
                   [:tr
                    [:td.name.num (or (:numero_apolice policy) "-")]
                    [:td (:client_name policy)]
                    [:td.right.strong-num
                     (str "R$ " (or (fmt-int (:mrr_for_commission policy)) "0"))]
                    [:td.right.num (str (or (:achievement_pct policy) "0") "%")]
                    [:td.right.num (str (or (:commission_pct policy) "0") "%")]
                    [:td.right.num (str (or (:multiplier policy) "1,00") "x")]
                    [:td.right.strong-num
                     (str "R$ " (or (fmt-int (:commission_amount policy)) "0"))]
                    [:td (case (:commission_status policy)
                           "SETTLED" [:span.badge.badge-paid "OK"]
                           "PROJECTED" [:span.badge.badge-paid "OK"]
                           "IN_PAYMENT" [:span.badge.badge-review "Verificar"]
                           [:span.badge.badge-review "Verificar"])]]))]]]])]))))
