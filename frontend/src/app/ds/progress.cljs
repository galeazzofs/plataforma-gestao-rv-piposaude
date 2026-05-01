(ns app.ds.progress
  (:require [app.ds.tokens :as t]))

;; Progress bars — match the design's .bar / .bar-fill / .cell-progress.

(defn progress-bar
  "Simple horizontal bar.
   Props: value (0-100), color, height, show-label?"
  [{:keys [value color height show-label?]}]
  (let [pct (min (max (or value 0) 0) 100)
        h   (or height "6px")
        clr (or color t/text-primary)]
    [:div {:style {:display "flex" :flex-direction "column" :gap "4px"}}
     (when show-label?
       [:span {:style {:font-family t/font-mono :font-size "11px" :color t/text-tertiary}}
        (str (.toFixed pct 0) "%")])
     [:div {:style {:width "100%" :height h
                    :background t/border-default
                    :border-radius "9999px" :overflow "hidden"}}
      [:div {:style {:width (str pct "%")
                     :height "100%" :background clr
                     :border-radius "9999px"
                     :transition (str "width " t/transition-default)}}]]]))

(defn achievement-bar
  "Goal achievement bar with current/target labels.
   Props: value (0-100), target-label, current-label"
  [{:keys [value target-label current-label]}]
  (let [pct (min (max (or value 0) 0) 100)
        bar-class (cond (>= pct 100) "success" (>= pct 70) "warn" :else "danger")]
    [:div {:style {:display "flex" :flex-direction "column" :gap "8px"}}
     [:div {:style {:display "flex" :justify-content "space-between"}}
      (when current-label
        [:span {:style {:font-family t/font-ui :font-size "13px" :font-weight 600
                        :color t/text-primary}}
         current-label])
      (when target-label
        [:span {:style {:font-family t/font-mono :font-size "12px" :color t/text-tertiary}}
         target-label])]
     [:div.bar {:style {:height "10px"}}
      [:div {:class (str "bar-fill " bar-class)
             :style {:width (str pct "%")}}]]
     [:span {:style {:font-family t/font-mono :font-size "11px" :color t/text-tertiary
                     :text-align "right"}}
      (str (.toFixed pct 1) "% da meta")]]))
