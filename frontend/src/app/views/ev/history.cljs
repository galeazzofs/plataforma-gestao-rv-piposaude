(ns app.views.ev.history
  (:require [re-frame.core :as rf]
            [reagent.core :as r]
            [app.ds.layout :as layout]
            [app.ds.cards :as cards]
            [app.ds.inputs :as inputs]
            [app.ds.buttons :as btn]
            [app.ds.tokens :as t]
            [app.views.ev.deals-table :as deals-table]
            [app.auth.subs]))

(def sidebar-items
  [{:key :ev/dashboard  :label "Dashboard"  :icon "📊" :route :ev/dashboard}
   {:key :ev/history    :label "Histórico"  :icon "📅" :route :ev/history}
   {:key :ev/validation :label "Validação"  :icon "✓"  :route :ev/validation}])

(defn quarter-options []
  [{:value "" :label "Todos os trimestres"}
   {:value "1" :label "Q1"}
   {:value "2" :label "Q2"}
   {:value "3" :label "Q3"}
   {:value "4" :label "Q4"}])

(defn year-options []
  (let [current-year 2026]
    (into [{:value "" :label "Todos os anos"}]
          (map (fn [y] {:value (str y) :label (str y)})
               (range current-year (- current-year 5) -1)))))

(defn status-options []
  [{:value "" :label "Todos os status"}
   {:value "PROJECTED"  :label "Projetado"}
   {:value "IN_PAYMENT" :label "Em pagamento"}
   {:value "SETTLED"    :label "Quitado"}
   {:value "CANCELLED"  :label "Cancelado"}])

(defn history-page []
  (let [filters (r/atom {:quarter nil :year nil :status nil})]
    (rf/dispatch [:ev/fetch-policies @filters])
    (fn []
      (let [policies     @(rf/subscribe [:ev/policies])
            pol-meta     @(rf/subscribe [:ev/policies-meta])
            loading?     @(rf/subscribe [:ev/policies-loading?])
            user         @(rf/subscribe [:auth/current-user])
            route        @(rf/subscribe [:current-route-name])]
        [layout/page-shell
         {:sidebar-items sidebar-items
          :current-route route
          :user          user
          :title         "Histórico"
          :subtitle      "Negócios por trimestre e ano"}

         ;; Filter bar
         [cards/card {:style {:margin-bottom "24px"}}
          [:div {:style {:display "flex" :gap "16px" :align-items "flex-end" :flex-wrap "wrap"}}
           [:div {:style {:flex "1" :min-width "140px"}}
            [inputs/select
             {:label     "Trimestre"
              :value     (or (:quarter @filters) "")
              :options   (quarter-options)
              :on-change #(swap! filters assoc :quarter (when-not (clojure.string/blank? %) %))}]]
           [:div {:style {:flex "1" :min-width "140px"}}
            [inputs/select
             {:label     "Ano"
              :value     (or (:year @filters) "")
              :options   (year-options)
              :on-change #(swap! filters assoc :year (when-not (clojure.string/blank? %) %))}]]
           [:div {:style {:flex "1" :min-width "140px"}}
            [inputs/select
             {:label     "Status"
              :value     (or (:status @filters) "")
              :options   (status-options)
              :on-change #(swap! filters assoc :status (when-not (clojure.string/blank? %) %))}]]
           [btn/button
            {:variant  :primary
             :on-click #(rf/dispatch [:ev/fetch-policies @filters])}
            "Filtrar"]]]

         ;; Table
         [cards/card {}
          [deals-table/deals-table
           {:rows        policies
            :loading?    loading?
            :page        (or (:page pol-meta) 1)
            :total-pages (or (:total_pages pol-meta) 1)
            :on-page-change (fn [p]
                              (rf/dispatch [:ev/fetch-policies
                                            (assoc @filters :page p)]))}]]]))))
