(ns app.views.finance.fluxo-caixa
  (:require [app.ds.charts :as charts]
            [app.ds.tokens :as t]))

(defn fluxo-caixa-chart
  "Cash flow line chart: realizado vs projetado.
   data: [{:month \"Jan\" :realizado 1000 :projetado 1200} ...]"
  [data]
  [:div
   [:h3 {:style {:font-size (:lg t/font-sizes)
                 :font-weight (:semibold t/font-weights)
                 :margin "0 0 16px 0"}} "Fluxo de Caixa"]
   [charts/line-chart
    {:data  (or data [])
     :x-key :month
     :lines [{:key     :realizado
              :color   (first t/chart-colors)
              :label   "Realizado"}
             {:key     :projetado
              :color   (second t/chart-colors)
              :label   "Projetado"
              :dashed  true}]}]])
