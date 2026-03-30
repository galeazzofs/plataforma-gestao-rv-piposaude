(ns app.ds.charts
  (:require [app.ds.tokens :as t]
            ["recharts" :as rc]))

(defn bar-chart
  "Bar chart wrapper.
   data: [{:name \"Jan\" :value 1000} ...]
   Props: x-key, bar-key, color, height"
  [{:keys [data x-key bar-key color height]}]
  [:> rc/ResponsiveContainer {:width "100%" :height (or height 300)}
   [:> rc/BarChart {:data (clj->js data)
                    :margin #js {:top 5 :right 20 :left 20 :bottom 5}}
    [:> rc/CartesianGrid {:strokeDasharray "3 3" :stroke t/bg-subtle}]
    [:> rc/XAxis {:dataKey (name (or x-key :name))
                  :tick #js {:fontSize 12 :fill t/text-secondary}}]
    [:> rc/YAxis {:tick #js {:fontSize 12 :fill t/text-secondary}}]
    [:> rc/Tooltip {:contentStyle #js {:borderRadius "8px" :border "none" :boxShadow (:md t/shadows)}}]
    [:> rc/Bar {:dataKey (name (or bar-key :value))
                :fill (or color (first t/chart-colors))
                :radius #js [4 4 0 0]}]]])

(defn line-chart
  "Line chart wrapper.
   data: [{:name \"Jan\" :actual 1000 :projected 1200} ...]
   lines: [{:key :actual :color \"blue\" :label \"Real\"} ...]"
  [{:keys [data lines x-key height]}]
  [:> rc/ResponsiveContainer {:width "100%" :height (or height 300)}
   [:> rc/LineChart {:data (clj->js data)
                     :margin #js {:top 5 :right 20 :left 20 :bottom 5}}
    [:> rc/CartesianGrid {:strokeDasharray "3 3" :stroke t/bg-subtle}]
    [:> rc/XAxis {:dataKey (name (or x-key :name))
                  :tick #js {:fontSize 12 :fill t/text-secondary}}]
    [:> rc/YAxis {:tick #js {:fontSize 12 :fill t/text-secondary}}]
    [:> rc/Tooltip {:contentStyle #js {:borderRadius "8px" :border "none" :boxShadow (:md t/shadows)}}]
    [:> rc/Legend]
    (for [{:keys [key color label dashed]} lines]
      ^{:key key}
      [:> rc/Line {:type "monotone"
                   :dataKey (name key)
                   :stroke (or color (first t/chart-colors))
                   :name label
                   :strokeWidth 2
                   :strokeDasharray (when dashed "5 5")
                   :dot false}])]])
