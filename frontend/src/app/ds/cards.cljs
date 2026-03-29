(ns app.ds.cards
  (:require [app.ds.tokens :as t]))

(defn card
  "Card container."
  [{:keys [padding class style]} & children]
  (into [:div {:style (merge {:background t/bg-card
                              :border-radius (:lg t/border-radius)
                              :padding (or padding (:card t/padding))
                              :box-shadow (:card t/shadows)}
                             style)
               :class class}]
        children))

(defn stat-card
  "Stat card with label, value, and optional change indicator.
   color: :default :success :warning :error"
  [{:keys [label value subtitle color]}]
  (let [accent (case (or color :default)
                 :success t/success-default
                 :warning t/warning-default
                 :error   t/error-default
                 t/color-primary)]
    [card {}
     [:div {:style {:display "flex" :flex-direction "column" :gap "4px"}}
      [:span {:style {:font-size (:xs t/font-sizes) :color t/text-secondary :text-transform "uppercase" :letter-spacing "0.05em" :font-weight (:medium t/font-weights)}} label]
      [:span {:style {:font-size (:3xl t/font-sizes) :font-weight (:bold t/font-weights) :color accent}} value]
      (when subtitle
        [:span {:style {:font-size (:sm t/font-sizes) :color t/text-secondary}} subtitle])]]))

(defn progress-card
  "Card with progress bar for achievement tracking."
  [{:keys [label current target percentage]}]
  (let [pct (or percentage (if (and current target (> target 0))
                             (* 100 (/ current target))
                             0))
        bar-color (cond
                    (>= pct 100) t/success-default
                    (>= pct 50)  t/warning-default
                    :else        t/error-default)]
    [card {}
     [:div {:style {:display "flex" :flex-direction "column" :gap "8px"}}
      [:span {:style {:font-size (:xs t/font-sizes) :color t/text-secondary :text-transform "uppercase" :letter-spacing "0.05em" :font-weight (:medium t/font-weights)}} label]
      [:div {:style {:display "flex" :justify-content "space-between" :align-items "baseline"}}
       [:span {:style {:font-size (:2xl t/font-sizes) :font-weight (:bold t/font-weights)}} (str (.toFixed pct 1) "%")]
       (when (and current target)
         [:span {:style {:font-size (:sm t/font-sizes) :color t/text-secondary}}
          (str "R$ " (.toLocaleString current "pt-BR") " / R$ " (.toLocaleString target "pt-BR"))])]
      ;; Progress bar
      [:div {:style {:width "100%" :height "8px" :background t/bg-subtle :border-radius (:full t/border-radius) :overflow "hidden"}}
       [:div {:style {:width (str (min pct 100) "%")
                      :height "100%"
                      :background bar-color
                      :border-radius (:full t/border-radius)
                      :transition t/transition-default}}]]]]))
