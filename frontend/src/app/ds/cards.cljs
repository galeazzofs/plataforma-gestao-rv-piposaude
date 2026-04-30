(ns app.ds.cards
  (:require [app.ds.tokens :as t]))

(defn card
  "Card container, matching the .card spec from the Pipo design."
  [{:keys [padding class style]} & children]
  (into [:div {:style (merge {:background t/bg-card
                              :border (str "1px solid " t/border-default)
                              :border-radius (:lg t/border-radius)
                              :padding (or padding (:card t/padding))
                              :display "flex" :flex-direction "column" :gap "16px"}
                             style)
               :class class}]
        children))

(defn stat-card
  "KPI card. Big display-font value, mono uppercase label, optional subtitle."
  [{:keys [label value subtitle color icon]}]
  (let [accent (case (or color :default)
                 :success t/success-default
                 :warning t/warning-default
                 :error   t/error-default
                 t/text-primary)]
    [:div {:style {:background t/bg-card
                   :border (str "1px solid " t/border-default)
                   :border-radius (:lg t/border-radius)
                   :padding "20px"
                   :display "flex" :flex-direction "column" :gap "12px"
                   :position "relative" :overflow "hidden"}}
     [:span {:style {:font-family t/font-mono :font-size "11px"
                     :text-transform "lowercase" :letter-spacing "0.02em"
                     :color t/text-tertiary
                     :display "flex" :align-items "center" :gap "6px"}}
      (when icon [:span {:style {:font-size "14px"}} icon])
      label]
     [:span {:style {:font-family t/font-display :font-size "38px" :line-height "1"
                     :font-weight "400" :color accent
                     :letter-spacing "-0.01em"}}
      value]
     (when subtitle
       [:span {:style {:font-size "12px" :color t/text-tertiary :margin-top "auto"}} subtitle])]))

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
     [:div {:style {:display "flex" :flex-direction "column" :gap "12px"}}
      [:span {:style {:font-family t/font-mono :font-size "11px"
                      :text-transform "lowercase" :letter-spacing "0.02em"
                      :color t/text-tertiary}}
       label]
      [:div {:style {:display "flex" :justify-content "space-between" :align-items "baseline"}}
       [:span {:style {:font-family t/font-display :font-size "38px"
                       :font-weight "400" :line-height "1"
                       :color bar-color :letter-spacing "-0.01em"}}
        (str (.toFixed pct 1) "%")]
       (when (and current target)
         [:span {:style {:font-family t/font-mono :font-size "11px" :color t/text-tertiary}}
          (str "R$ " (.toLocaleString current "pt-BR") " / R$ " (.toLocaleString target "pt-BR"))])]
      [:div {:style {:width "100%" :height "6px"
                     :background t/border-default
                     :border-radius (:full t/border-radius) :overflow "hidden"}}
       [:div {:style {:width (str (min pct 100) "%")
                      :height "100%"
                      :background bar-color
                      :border-radius (:full t/border-radius)
                      :transition (str "width " t/transition-default)}}]]]]))
