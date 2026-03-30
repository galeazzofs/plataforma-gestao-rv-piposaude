(ns app.views.finance.export
  (:require [re-frame.core :as rf]
            [reagent.core :as r]
            [app.ds.cards :as cards]
            [app.ds.inputs :as inputs]
            [app.ds.buttons :as btn]
            [app.ds.tokens :as t]))

(defn format-options []
  [{:value "xlsx" :label "Excel (.xlsx)"}
   {:value "csv"  :label "CSV (.csv)"}
   {:value "pdf"  :label "PDF (.pdf)"}])

(defn export-panel
  "Standalone export panel: format select, filter, download trigger."
  []
  (let [fmt     (r/atom "xlsx")
        quarter (r/atom "")
        year    (r/atom "")
        ev-id   (r/atom "")]
    (fn []
      [cards/card {}
       [:div {:style {:display "flex" :flex-direction "column" :gap "20px"}}
        [:h3 {:style {:font-size (:lg t/font-sizes)
                      :font-weight (:semibold t/font-weights)
                      :margin "0"}} "Exportar Dados"]

        [:div {:style {:display "grid" :grid-template-columns "1fr 1fr 1fr 1fr" :gap "16px"}}
         [inputs/select
          {:label     "Formato"
           :value     @fmt
           :options   (format-options)
           :on-change #(reset! fmt %)}]
         [inputs/select
          {:label     "Trimestre"
           :value     @quarter
           :options   [{:value "" :label "Todos"}
                       {:value "1" :label "Q1"}
                       {:value "2" :label "Q2"}
                       {:value "3" :label "Q3"}
                       {:value "4" :label "Q4"}]
           :on-change #(reset! quarter %)}]
         [inputs/select
          {:label     "Ano"
           :value     @year
           :options   [{:value "" :label "Todos"}
                       {:value "2026" :label "2026"}
                       {:value "2025" :label "2025"}]
           :on-change #(reset! year %)}]
         [inputs/input
          {:label       "EV (opcional)"
           :value       @ev-id
           :placeholder "ID do EV"
           :on-change   #(reset! ev-id %)}]]

        [:div {:style {:display "flex" :justify-content "flex-end"}}
         [btn/button
          {:variant  :primary
           :on-click (fn []
                       (let [params (cond-> {:format @fmt}
                                      (seq @quarter) (assoc :quarter @quarter)
                                      (seq @year)    (assoc :year @year)
                                      (seq @ev-id)   (assoc :ev_id @ev-id))]
                         (rf/dispatch [:finance/export params])))}
          "Baixar Relatório"]]]])))
