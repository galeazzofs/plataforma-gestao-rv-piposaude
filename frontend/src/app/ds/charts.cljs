(ns app.ds.charts
  (:require [clojure.string :as str]))

;; Pipo-themed lightweight chart helpers — pure SVG, no external deps.
;; The dashboard view files (Finance, EV, History) draw their own SVG charts
;; tuned to the design; these wrappers exist for legacy callers.

(defn- max-of
  ([data ks]
   (->> data
        (mapcat (fn [d] (map #(get d %) ks)))
        (filter some?)
        (reduce max 1))))

(defn bar-chart
  "Vertical bar chart in Pipo styling.
   data: [{:name \"Jan\" :value 1000} ...]
   Props: x-key, bar-key, color, height"
  [{:keys [data x-key bar-key color height]}]
  (let [data (vec data)
        n    (count data)
        h    (or height 240)
        max-v (or (max-of data [(or bar-key :value)]) 1)
        slot  (/ 540 (max 1 n))
        x-of  (fn [i] (+ 60 (* i slot)))
        y-of  (fn [v] (- (- h 20) (* (/ v max-v) (- h 60))))
        clr   (or color "#000")]
    [:svg.chart {:viewBox (str "0 0 600 " h) :preserveAspectRatio "none"
                 :style {:width "100%" :height (str h "px") :display "block"}}
     [:g {:stroke "#E2E1DF" :stroke-width 1}
      [:line {:x1 40 :y1 (* h 0.17) :x2 600 :y2 (* h 0.17)}]
      [:line {:x1 40 :y1 (* h 0.42) :x2 600 :y2 (* h 0.42)}]
      [:line {:x1 40 :y1 (* h 0.67) :x2 600 :y2 (* h 0.67)}]
      [:line {:x1 40 :y1 (* h 0.92) :x2 600 :y2 (* h 0.92)}]]
     [:g
      (for [[i d] (map-indexed vector data)
            :let [v (get d (or bar-key :value))
                  y (y-of v)]
            :when (some? v)]
        ^{:key i}
        [:rect {:x (- (x-of i) 16) :y y :width 32 :height (- (- h 20) y)
                :fill clr :rx 2}])]
     [:g {:font-family "Manrope" :font-size 11 :fill "#6B6663"}
      (for [[i d] (map-indexed vector data)]
        ^{:key i}
        [:text {:x (- (x-of i) 12) :y (- h 6)} (get d (or x-key :name))])]]))

(defn line-chart
  "Multi-line chart in Pipo styling.
   data: [{:name \"Jan\" :actual 1000 :projected 1200} ...]
   lines: [{:key :actual :color \"#000\" :label \"Real\" :dashed false} ...]"
  [{:keys [data lines x-key height]}]
  (let [data (vec data)
        n    (count data)
        h    (or height 240)
        ks   (map :key lines)
        max-v (or (max-of data ks) 1)
        slot  (/ 540 (max 1 (dec (max 1 n))))
        x-of  (fn [i] (+ 60 (* i slot)))
        y-of  (fn [v] (- (- h 20) (* (/ (or v 0) max-v) (- h 60))))]
    [:svg.chart {:viewBox (str "0 0 600 " h) :preserveAspectRatio "none"
                 :style {:width "100%" :height (str h "px") :display "block"}}
     [:g {:stroke "#E2E1DF" :stroke-width 1}
      [:line {:x1 40 :y1 (* h 0.17) :x2 600 :y2 (* h 0.17)}]
      [:line {:x1 40 :y1 (* h 0.42) :x2 600 :y2 (* h 0.42)}]
      [:line {:x1 40 :y1 (* h 0.67) :x2 600 :y2 (* h 0.67)}]
      [:line {:x1 40 :y1 (* h 0.92) :x2 600 :y2 (* h 0.92)}]]
     (for [{:keys [key color dashed]} lines
           :let [pts (->> data
                          (map-indexed (fn [i d] (when-let [v (get d key)]
                                                   (str (x-of i) " " (y-of v)))))
                          (filter some?))]]
       ^{:key (str "line-" (name key))}
       [:path {:d (str "M " (str/join " L " pts))
               :fill "none"
               :stroke (or color "#000")
               :stroke-width 2.5
               :stroke-dasharray (when dashed "6 4")
               :stroke-linecap "round"}])
     [:g {:font-family "Manrope" :font-size 11 :fill "#6B6663"}
      (for [[i d] (map-indexed vector data)]
        ^{:key i}
        [:text {:x (- (x-of i) 12) :y (- h 6)} (get d (or x-key :name))])]]))
