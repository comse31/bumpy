components {
  id: "sprite"
  component: "/main/goodies/fruit/fruit.sprite"
}
components {
  id: "goodie"
  component: "/main/goodies/fruit/fruit.script"
  properties {
    id: "kind"
    type: PROPERTY_TYPE_NUMBER
    value: "3"
  }
  properties {
    id: "collected"
    type: PROPERTY_TYPE_NUMBER
    value: "0"
  }
  properties {
    id: "anim"
    type: PROPERTY_TYPE_HASH
    value: "apple"
  }
}
