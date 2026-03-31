(ns app.ds.cards
  (:require [app.ds.tokens :as t]))

(defn card
  "Card container."
  [{:keys [padding class style]} & children]
  (into [:div {:style (merge {:background t/bg-card
                              :border-radius (:lg t/border-radius)
                              :padding (or padding (:card t/padding))
                              :box-shadow (:card t/shadows)
                              :border (str "1px solid " t/border-default)}
                             style)
               :class class}]
        children))

(defn stat-card
  "Stat card with label, value, and optional change indicator.
   color: :default :success :warning :error"
  [{:keys [label value subtitle color icon]}]
  (let [accent (case (or color :default)
                 :success t/success-default
                 :warning t/warning-default
                 :error   t/error-default
                 t/color-primary)
        bg     (case (or color :default)
                 :success t/success-light
                 :warning t/warning-light
                 :error   t/error-light
                 t/beige-100)]
    [card {}
     [:div {:style {:display "flex" :flex-direction "column" :gap "12px"}}
      (when icon
        [:div {:style {:width "40px" :height "40px" :border-radius (:md t/border-radius)
                       :background bg :display "flex" :align-items "center"
                       :justify-content "center" :font-size "20px"}}
         icon])
      [:div {:style {:display "flex" :flex-direction "column" :gap "4px"}}
       [:span {:style {:font-size (:xs t/font-sizes) :color t/text-secondary
                       :text-transform "uppercase" :letter-spacing "0.06em"
                       :font-weight (:semibold t/font-weights)}} label]
       [:span {:style {:font-size (:3xl t/font-sizes) :font-weight (:bold t/font-weights)
                       :color accent :line-height "1.1"}} value]
       (when subtitle
         [:span {:style {:font-size (:xs t/font-sizes) :color t/text-secondary}} subtitle])]]]))

(defn progress-card
  "Card with progress bar for achievement tracking."
  [{:keys [label current target percentage]}]
  (let [pct (or percentage (if (and current target (> target 0))
                             (* 100 (/ current target))
                             0))
        bar-color (cond
                    (>= pct 100) t/success-default
                    (>= pct 50)  t/warning-default
                    :else        t/error-default)
        bg-color  (cond
                    (>= pct 100) t/success-light
                    (>= pct 50)  t/warning-light
                    :else        t/error-light)]
    [card {}
     [:div {:style {:display "flex" :flex-direction "column" :gap "12px"}}
      [:span {:style {:font-size (:xs t/font-sizes) :color t/text-secondary
                      :text-transform "uppercase" :letter-spacing "0.06em"
                      :font-weight (:semibold t/font-weights)}} label]
      [:div {:style {:display "flex" :justify-content "space-between" :align-items "baseline"}}
       [:span {:style {:font-size (:3xl t/font-sizes) :font-weight (:bold t/font-weights)
                       :color bar-color :line-height "1.1"}}
        (str (.toFixed pct 1) "%")]
       (when (and current target)
         [:span {:style {:font-size (:xs t/font-sizes) :color t/text-secondary}}
          (str "R$ " (.toLocaleString current "pt-BR") " / R$ " (.toLocaleString target "pt-BR"))])]
      ;; Progress bar track
      [:div {:style {:width "100%" :height "6px" :background bg-color
                     :border-radius (:full t/border-radius) :overflow "hidden"}}
       [:div {:style {:width (str (min pct 100) "%")
                      :height "100%"
                      :background bar-color
                      :border-radius (:full t/border-radius)
                      :transition t/transition-default}}]]]]))
