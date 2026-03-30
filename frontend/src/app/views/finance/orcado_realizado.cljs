(ns app.views.finance.orcado-realizado
  (:require [app.ds.charts :as charts]
            [app.ds.tokens :as t]
            ["recharts" :as rc]))

(defn orcado-realizado-chart
  "Budget vs actual grouped bar chart.
   data: [{:quarter \"Q1/2026\" :orcado 10000 :realizado 9500} ...]"
  [data]
  [:div
   [:h3 {:style {:font-size (:lg t/font-sizes)
                 :font-weight (:semibold t/font-weights)
                 :margin "0 0 16px 0"}} "Orçado vs Realizado"]
   [:> rc/ResponsiveContainer {:width "100%" :height 300}
    [:> rc/BarChart {:data (clj->js (or data []))
                     :margin #js {:top 5 :right 20 :left 20 :bottom 5}}
     [:> rc/CartesianGrid {:strokeDasharray "3 3" :stroke t/bg-subtle}]
     [:> rc/XAxis {:dataKey "quarter"
                   :tick #js {:fontSize 12 :fill t/text-secondary}}]
     [:> rc/YAxis {:tick #js {:fontSize 12 :fill t/text-secondary}}]
     [:> rc/Tooltip {:contentStyle #js {:borderRadius "8px" :border "none" :boxShadow (:md t/shadows)}}]
     [:> rc/Legend]
     [:> rc/Bar {:dataKey  "orcado"
                 :name     "Orçado"
                 :fill     (first t/chart-colors)
                 :radius   #js [4 4 0 0]}]
     [:> rc/Bar {:dataKey  "realizado"
                 :name     "Realizado"
                 :fill     (second t/chart-colors)
                 :radius   #js [4 4 0 0]}]]]])
