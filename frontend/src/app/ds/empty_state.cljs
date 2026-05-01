(ns app.ds.empty-state
  (:require [app.ds.layout :as layout]
            [app.ds.buttons :as btn]))

;; Empty state — uses the design's .empty + .empty-illus classes.

(defn empty-state
  "Empty state placeholder.
   Props: title, description, action-label, on-action, icon (symbol id like \"target\")"
  [{:keys [title description action-label on-action icon]}]
  [:div.empty
   [:div.empty-illus
    [layout/icon (or icon "empty") {:width 40 :height 40}]]
   [:h4 (or title "Nenhum resultado encontrado")]
   (when description [:p description])
   (when (and action-label on-action)
     [btn/button {:variant :primary :size :sm :on-click on-action}
      action-label])])
