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
    (let [n (if (string? v) (js/parseFloat v) v)]
      (str "R$ " (.toLocaleString n "pt-BR" #js {:minimumFractionDigits 2 :maximumFractionDigits 2})))))

(defn summary-cards [summary]
  [:div {:style {:display "grid"
                 :grid-template-columns "repeat(auto-fit, minmax(250px, 1fr))"
                 :gap "20px"}}
   [cards/stat-card
    {:label    "Saldo a Receber"
     :value    (fmt-brl (or (:balance_estimated summary) 0))
     :subtitle "Comissões em aberto"
     :icon     "💰"
     :color    :default}]
   [cards/progress-card
    {:label      "Atingimento do Período"
     :current    (or (:mrr_sold summary) 0)
     :target     (or (:mrr_target summary) 1)
     :percentage (or (:achievement_pct summary) 0)}]
   [cards/stat-card
    {:label    "Meta do Período"
     :value    (fmt-brl (or (:mrr_target summary) 0))
     :subtitle (str "Q" (or (:current_quarter summary) "-") "/" (or (:current_year summary) "-"))
     :icon     "🎯"
     :color    :default}]])

(defn projection-chart [projection]
  [cards/card {}
   [:div {:style {:display "flex" :justify-content "space-between" :align-items "center" :margin-bottom "20px"}}
    [:div
     [:h3 {:style {:font-size (:lg t/font-sizes) :font-weight (:semibold t/font-weights)
                   :margin "0" :color t/text-primary}} "Projeção Mensal"]
     [:span {:style {:font-size (:xs t/font-sizes) :color t/text-secondary}} "Projetado vs. Realizado"]]]
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
         [:div {:style {:display "grid"
                        :grid-template-columns "repeat(auto-fit, minmax(250px, 1fr))"
                        :gap "20px"}}
          (for [i (range 3)]
            ^{:key i}
            [:div {:style {:background t/bg-card :border-radius (:lg t/border-radius)
                           :height "120px" :border (str "1px solid " t/border-default)}}])]
         [summary-cards summary])

       ;; Projection chart
       (when-not loading?
         [projection-chart projection])

       ;; Deals table
       [cards/card {}
        [:div {:style {:display "flex" :justify-content "space-between" :align-items "center" :margin-bottom "16px"}}
         [:div
          [:h3 {:style {:font-size (:lg t/font-sizes) :font-weight (:semibold t/font-weights)
                        :margin "0" :color t/text-primary}} "Negócios"]
          [:span {:style {:font-size (:xs t/font-sizes) :color t/text-secondary}} "Todas as apólices do período"]]]
        [deals-table/deals-table
         {:rows     policies
          :loading? pol-loading?}]]])))
