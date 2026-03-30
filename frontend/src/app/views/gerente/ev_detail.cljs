(ns app.views.gerente.ev-detail
  (:require [re-frame.core :as rf]
            [app.ds.layout :as layout]
            [app.ds.cards :as cards]
            [app.ds.buttons :as btn]
            [app.ds.tokens :as t]
            [app.views.ev.deals-table :as deals-table]
            [app.auth.subs]))

(def sidebar-items
  [{:key :gerente/dashboard :label "Dashboard (Time)" :icon "👥" :route :gerente/dashboard}])

(defn fmt-brl [v]
  (when v
    (str "R$ " (.toLocaleString v "pt-BR" #js {:minimumFractionDigits 2 :maximumFractionDigits 2}))))

(defn ev-summary-cards [ev-data]
  [:div {:style {:display "grid"
                 :grid-template-columns "repeat(3, 1fr)"
                 :gap "24px"
                 :margin-bottom "32px"}}
   [cards/stat-card
    {:label    "Saldo a Receber"
     :value    (fmt-brl (or (:saldo ev-data) 0))
     :subtitle "Em aberto"}]
   [cards/progress-card
    {:label      "Atingimento"
     :current    (or (:commission_total ev-data) 0)
     :target     (or (:goal_amount ev-data) 1)
     :percentage (or (:achievement_pct ev-data) 0)}]
   [cards/stat-card
    {:label    "Meta do Período"
     :value    (fmt-brl (or (:goal_amount ev-data) 0))
     :subtitle (str "Q" (or (:quarter ev-data) "-") "/" (or (:year ev-data) "-"))}]])

(defn ev-detail-page []
  (let [route-params (rf/subscribe [:current-route])]
    (fn []
      (let [ev-id    (get-in @route-params [:path-params :ev-id])
            _        (when ev-id (rf/dispatch [:gerente/fetch-ev-detail ev-id]))
            ev-data  @(rf/subscribe [:gerente/ev-detail])
            loading? @(rf/subscribe [:gerente/ev-detail-loading?])
            user     @(rf/subscribe [:auth/current-user])
            route    @(rf/subscribe [:current-route-name])]
        [layout/page-shell
         {:sidebar-items sidebar-items
          :current-route route
          :user          user
          :title         (str "EV: " (or (:name ev-data) "Carregando..."))
          :subtitle      "Visão somente leitura"
          :header-actions
          [btn/button
           {:variant  :secondary
            :on-click #(rf/dispatch [:navigate! :gerente/dashboard])}
           "← Voltar ao time"]}

         (if loading?
           [:div {:style {:color t/text-secondary}} "Carregando..."]
           [:<>
            [ev-summary-cards (or ev-data {})]
            [cards/card {}
             [:h3 {:style {:font-size (:lg t/font-sizes)
                           :font-weight (:semibold t/font-weights)
                           :margin-bottom "16px"}} "Negócios"]
             [deals-table/deals-table
              {:rows (or (:policies ev-data) [])}]]])]))))
