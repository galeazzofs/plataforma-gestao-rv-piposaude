(ns app.ds.empty-state
  (:require [app.ds.tokens :as t]
            [app.ds.buttons :as btn]))

(defn empty-state
  "Empty state placeholder component.
   Props: title, description, action-label, on-action, icon"
  [{:keys [title description action-label on-action icon]}]
  [:div {:style {:display "flex"
                 :flex-direction "column"
                 :align-items "center"
                 :justify-content "center"
                 :padding "64px 32px"
                 :text-align "center"
                 :gap "16px"}}
   ;; Icon / illustration
   [:div {:style {:font-size "48px"
                  :color t/text-disabled
                  :margin-bottom "8px"}}
    (or icon "📭")]
   ;; Title
   [:h3 {:style {:font-size (:xl t/font-sizes)
                 :font-weight (:semibold t/font-weights)
                 :color t/text-primary
                 :margin "0"}}
    (or title "Nenhum resultado encontrado")]
   ;; Description
   (when description
     [:p {:style {:font-size (:sm t/font-sizes)
                  :color t/text-secondary
                  :margin "0"
                  :max-width "360px"}}
      description])
   ;; CTA button
   (when (and action-label on-action)
     [btn/button {:variant :primary :on-click on-action}
      action-label])])
