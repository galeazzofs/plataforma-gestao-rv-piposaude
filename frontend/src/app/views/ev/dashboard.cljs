(ns app.views.ev.dashboard
  (:require [re-frame.core :as rf]
            [app.ds.layout :as layout]
            [app.ds.cards :as cards]
            [app.ds.charts :as charts]
            [app.ds.tokens :as t]
            [app.views.ev.deals-table :as deals-table]
            [app.auth.subs]))

(def sidebar-items
  [{:key :ev/dashboard  :label "Dashboard"  :icon "📊" :route :ev/dashboard}
   {:key :ev/history    :label "Histórico"  :icon "📅" :route :ev/history}
   {:key :ev/validation :label "Validação"  :icon "✓"  :route :ev/validation}])

(defn fmt-brl [v]
  (when v
    (str "R$ " (.toLocaleString v "pt-BR" #js {:minimumFractionDigits 2 :maximumFractionDigits 2}))))

(defn summary-cards [summary]
  [:div {:style {:display "grid"
                 :grid-template-columns "repeat(3, 1fr)"
                 :gap "24px"
                 :margin-bottom "32px"}}
   [cards/stat-card
    {:label    "Saldo a Receber"
     :value    (fmt-brl (or (:saldo summary) 0))
     :subtitle "Comissões em aberto"
     :color    :default}]
   [cards/progress-card
    {:label      "Atingimento"
     :current    (or (:commission_total summary) 0)
     :target     (or (:goal_amount summary) 1)
     :percentage (or (:achievement_pct summary) 0)}]
   [cards/stat-card
    {:label    "Meta do Período"
     :value    (fmt-brl (or (:goal_amount summary) 0))
     :subtitle (str "Q" (or (:quarter summary) "-") "/" (or (:year summary) "-"))
     :color    :default}]])

(defn projection-chart [projection]
  [:div {:style {:margin-bottom "32px"}}
   [:h3 {:style {:font-size (:lg t/font-sizes)
                 :font-weight (:semibold t/font-weights)
                 :margin-bottom "16px"}} "Projeção Mensal"]
   [charts/line-chart
    {:data  (or projection [])
     :x-key :month
     :lines [{:key :projected :color (first t/chart-colors)     :label "Projetado" :dashed true}
             {:key :actual    :color (second t/chart-colors)    :label "Realizado"}]}]])

(defn dashboard-page []
  (rf/dispatch [:ev/fetch-dashboard])
  (rf/dispatch [:ev/fetch-policies nil])
  (rf/dispatch [:ev/fetch-projection])
  (fn []
    (let [summary    @(rf/subscribe [:ev/summary])
          projection @(rf/subscribe [:ev/projection])
          policies   @(rf/subscribe [:ev/policies])
          loading?   @(rf/subscribe [:ev/loading?])
          pol-loading? @(rf/subscribe [:ev/policies-loading?])
          user       @(rf/subscribe [:auth/current-user])
          route      @(rf/subscribe [:current-route-name])]
      [layout/page-shell
       {:sidebar-items sidebar-items
        :current-route route
        :user          user
        :title         "Dashboard"
        :subtitle      (str "Bem-vindo, " (or (:name user) "EV"))}

       ;; Summary cards
       (if loading?
         [:div {:style {:color t/text-secondary :margin-bottom "32px"}} "Carregando..."]
         [summary-cards summary])

       ;; Projection chart
       (when-not loading?
         [projection-chart projection])

       ;; Deals table
       [:div
        [:h3 {:style {:font-size (:lg t/font-sizes)
                      :font-weight (:semibold t/font-weights)
                      :margin-bottom "16px"}} "Negócios"]
        [deals-table/deals-table
         {:rows     policies
          :loading? pol-loading?}]]])))
