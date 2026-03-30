(ns app.ds.progress
  (:require [app.ds.tokens :as t]))

(defn progress-bar
  "Simple horizontal progress bar.
   Props: value (0-100), color, height, show-label?"
  [{:keys [value color height show-label?]}]
  (let [pct   (min (max (or value 0) 0) 100)
        clr   (or color t/success-default)
        h     (or height "8px")]
    [:div {:style {:display "flex" :flex-direction "column" :gap "4px"}}
     (when show-label?
       [:span {:style {:font-size (:xs t/font-sizes) :color t/text-secondary}} (str (int pct) "%")])
     [:div {:style {:width "100%" :height h :background t/bg-subtle
                    :border-radius (:full t/border-radius) :overflow "hidden"}}
      [:div {:style {:width (str pct "%")
                     :height "100%"
                     :background clr
                     :border-radius (:full t/border-radius)
                     :transition t/transition-default}}]]]))

(defn achievement-bar
  "Progress bar styled for goal achievement with threshold markers.
   Props: value (0-100), target-label, current-label"
  [{:keys [value target-label current-label]}]
  (let [pct       (min (max (or value 0) 0) 100)
        bar-color (cond
                    (>= pct 100) t/success-default
                    (>= pct 75)  t/warning-default
                    (>= pct 50)  t/warning-default
                    :else        t/error-default)]
    [:div {:style {:display "flex" :flex-direction "column" :gap "8px"}}
     [:div {:style {:display "flex" :justify-content "space-between"}}
      (when current-label
        [:span {:style {:font-size (:sm t/font-sizes) :font-weight (:medium t/font-weights) :color t/text-primary}}
         current-label])
      (when target-label
        [:span {:style {:font-size (:sm t/font-sizes) :color t/text-secondary}}
         target-label])]
     [:div {:style {:position "relative" :width "100%" :height "12px"
                    :background t/bg-subtle :border-radius (:full t/border-radius) :overflow "hidden"}}
      [:div {:style {:width (str pct "%")
                     :height "100%"
                     :background bar-color
                     :border-radius (:full t/border-radius)
                     :transition t/transition-default}}]]
     [:span {:style {:font-size (:xs t/font-sizes) :color t/text-secondary :text-align "right"}}
      (str (.toFixed pct 1) "% da meta")]]))
